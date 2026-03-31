"""
SQLite 데이터베이스 관리 모듈
reviews, cs_items, alerts 테이블을 관리합니다.
"""
import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "review_data.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS reviews (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            channel               TEXT NOT NULL,
            product_name          TEXT,
            option_name           TEXT,
            customer_id           TEXT,
            order_number          TEXT,
            rating                INTEGER,
            content               TEXT,
            review_date           TEXT,
            review_id_on_channel  TEXT,
            collected_at          TEXT DEFAULT (datetime('now','localtime')),
            sentiment             TEXT DEFAULT 'neutral',
            issue_tags            TEXT DEFAULT '[]',
            is_risk               INTEGER DEFAULT 0,
            risk_reason           TEXT,
            reply_draft           TEXT,
            reply_status          TEXT DEFAULT 'pending',
            reply_posted_at       TEXT,
            UNIQUE(channel, review_date, content)
        );

        CREATE TABLE IF NOT EXISTS cs_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            channel       TEXT NOT NULL,
            product_name  TEXT,
            customer_id   TEXT,
            title         TEXT,
            content       TEXT,
            inquiry_date  TEXT,
            collected_at  TEXT DEFAULT (datetime('now','localtime')),
            sentiment     TEXT DEFAULT 'neutral',
            issue_tags    TEXT DEFAULT '[]',
            is_risk       INTEGER DEFAULT 0,
            risk_reason   TEXT,
            reply_draft   TEXT,
            reply_status  TEXT DEFAULT 'pending',
            reply_posted_at TEXT,
            item_id       TEXT,
            UNIQUE(channel, item_id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type  TEXT NOT NULL,
            channel     TEXT,
            message     TEXT NOT NULL,
            level       TEXT DEFAULT 'info',
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            resolved    INTEGER DEFAULT 0
        );
        """)


# ── reviews ────────────────────────────────────────

def upsert_review(data: dict) -> bool:
    """리뷰 저장 (중복 시 무시). 신규 저장 시 True 반환."""
    cols = [
        "channel", "product_name", "option_name", "customer_id",
        "order_number", "rating", "content", "review_date",
        "review_id_on_channel", "sentiment", "issue_tags", "is_risk",
        "risk_reason", "reply_draft", "reply_status"
    ]
    vals = [data.get(c) if c != "reply_status" else (data.get(c) or "pending") for c in cols]
    placeholders = ", ".join(["?"] * len(cols))
    col_str = ", ".join(cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT OR IGNORE INTO reviews ({col_str}) VALUES ({placeholders})",
            vals
        )
        return cur.rowcount > 0


def update_review_analysis(review_id: int, sentiment: str, issue_tags: list,
                            is_risk: bool, risk_reason: str = None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE reviews SET sentiment=?, issue_tags=?, is_risk=?, risk_reason=?
               WHERE id=?""",
            (sentiment, json.dumps(issue_tags, ensure_ascii=False),
             1 if is_risk else 0, risk_reason, review_id)
        )


def update_review_reply(review_id: int, reply_draft: str, status: str = "pending"):
    with get_conn() as conn:
        conn.execute(
            "UPDATE reviews SET reply_draft=?, reply_status=? WHERE id=?",
            (reply_draft, status, review_id)
        )


def mark_review_posted(review_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE reviews SET reply_status='posted', reply_posted_at=datetime('now','localtime') WHERE id=?",
            (review_id,)
        )


def get_reviews(channel: str = None, status: str = None,
                date_from: str = None, date_to: str = None,
                limit: int = 200) -> list:
    wheres, params = [], []
    if channel:
        wheres.append("channel=?"); params.append(channel)
    if status:
        wheres.append("reply_status=?"); params.append(status)
    if date_from:
        wheres.append("review_date>=?"); params.append(date_from)
    if date_to:
        wheres.append("review_date<=?"); params.append(date_to)
    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM reviews {where_sql} ORDER BY review_date DESC LIMIT ?",
            params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


def get_review_stats() -> dict:
    """채널별 통계 반환."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT channel,
                   COUNT(*) AS total,
                   AVG(rating) AS avg_rating,
                   SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) AS neg_count,
                   SUM(CASE WHEN reply_status='pending' THEN 1 ELSE 0 END) AS pending_count,
                   SUM(CASE WHEN is_risk=1 THEN 1 ELSE 0 END) AS risk_count
            FROM reviews
            GROUP BY channel
        """).fetchall()
    return {r["channel"]: dict(r) for r in rows}


def get_claim_rates() -> list:
    """상품/옵션별 클레임율 반환."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT product_name, option_name, channel,
                   COUNT(*) AS total,
                   SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) AS neg_count,
                   ROUND(100.0 * SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) / COUNT(*), 1) AS claim_rate
            FROM reviews
            WHERE product_name IS NOT NULL
            GROUP BY product_name, option_name, channel
            HAVING total >= 3
            ORDER BY claim_rate DESC
        """).fetchall()
    return [dict(r) for r in rows]


# ── cs_items ────────────────────────────────────────

def upsert_cs(data: dict) -> int:
    cols = [
        "channel", "product_name", "customer_id", "title", "content",
        "inquiry_date", "sentiment", "issue_tags", "is_risk", "risk_reason",
        "reply_draft", "reply_status", "item_id"
    ]
    vals = [data.get(c) for c in cols]
    placeholders = ", ".join(["?"] * len(cols))
    col_str = ", ".join(cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT OR IGNORE INTO cs_items ({col_str}) VALUES ({placeholders})",
            vals
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute(
            "SELECT id FROM cs_items WHERE channel=? AND item_id=?",
            (data.get("channel"), data.get("item_id"))
        ).fetchone()
        return row["id"] if row else None


def update_cs_reply(cs_id: int, reply_draft: str, status: str = "pending"):
    with get_conn() as conn:
        conn.execute(
            "UPDATE cs_items SET reply_draft=?, reply_status=? WHERE id=?",
            (reply_draft, status, cs_id)
        )


def mark_cs_posted(cs_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE cs_items SET reply_status='posted', reply_posted_at=datetime('now','localtime') WHERE id=?",
            (cs_id,)
        )


def get_cs_items(channel: str = None, status: str = None, limit: int = 200) -> list:
    wheres, params = [], []
    if channel:
        wheres.append("channel=?"); params.append(channel)
    if status:
        wheres.append("reply_status=?"); params.append(status)
    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM cs_items {where_sql} ORDER BY inquiry_date DESC LIMIT ?",
            params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


# ── alerts ────────────────────────────────────────

def add_alert(alert_type: str, message: str, level: str = "info", channel: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO alerts (alert_type, channel, message, level) VALUES (?,?,?,?)",
            (alert_type, channel, message, level)
        )


def get_unresolved_alerts() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE resolved=0 ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_alert(alert_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE alerts SET resolved=1 WHERE id=?", (alert_id,))


def check_and_create_alerts():
    """클레임율 기준치 초과 시 알림 생성."""
    CLAIM_THRESHOLD = 5.0
    rates = get_claim_rates()
    for r in rates:
        if r["claim_rate"] >= CLAIM_THRESHOLD:
            msg = (f"[{r['channel']}] '{r['product_name']}' "
                   f"클레임율 {r['claim_rate']}% (총 {r['total']}건 중 부정 {r['neg_count']}건)")
            level = "critical" if r["claim_rate"] >= 20 else "warning"
            add_alert("claim_rate", msg, level, r["channel"])


# 앱 시작 시 DB 초기화
init_db()
