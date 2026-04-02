import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = "automation.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── 초기화 / 마이그레이션 ───────────────────────────
def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                product_name TEXT,
                option_name TEXT,
                customer_id TEXT,
                order_number TEXT,
                rating INTEGER,
                content TEXT NOT NULL,
                review_date TEXT,
                review_id_on_channel TEXT NOT NULL,
                sentiment TEXT DEFAULT 'neutral',
                confidence REAL DEFAULT 0,
                issue_tags TEXT DEFAULT '[]',
                is_risk INTEGER DEFAULT 0,
                risk_reason TEXT,
                reply_draft TEXT,
                reply_status TEXT DEFAULT 'pending',
                posted_at TEXT,
                collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(channel, review_id_on_channel)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cs_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                product_name TEXT,
                customer_id TEXT,
                title TEXT,
                content TEXT NOT NULL,
                inquiry_date TEXT,
                item_id TEXT NOT NULL,
                sentiment TEXT DEFAULT 'neutral',
                confidence REAL DEFAULT 0,
                issue_tags TEXT DEFAULT '[]',
                is_risk INTEGER DEFAULT 0,
                risk_reason TEXT,
                reply_draft TEXT,
                reply_status TEXT DEFAULT 'pending',
                posted_at TEXT,
                collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(channel, item_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                channel TEXT,
                item_type TEXT,
                item_ref_id INTEGER,
                message TEXT NOT NULL,
                is_resolved INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_channel ON reviews(channel)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(reply_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_date ON reviews(review_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_collected ON reviews(collected_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_risk ON reviews(is_risk)")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_channel ON cs_items(channel)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_status ON cs_items(reply_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_date ON cs_items(inquiry_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_collected ON cs_items(collected_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_risk ON cs_items(is_risk)")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(is_resolved)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(level)")

        _run_safe_migrations(conn)


def _run_safe_migrations(conn):
    review_columns = {row[1] for row in conn.execute("PRAGMA table_info(reviews)").fetchall()}
    cs_columns = {row[1] for row in conn.execute("PRAGMA table_info(cs_items)").fetchall()}
    alert_columns = {row[1] for row in conn.execute("PRAGMA table_info(alerts)").fetchall()}

    review_additions = {
        "option_name": "TEXT",
        "customer_id": "TEXT",
        "order_number": "TEXT",
        "rating": "INTEGER",
        "review_date": "TEXT",
        "review_id_on_channel": "TEXT",
        "sentiment": "TEXT DEFAULT 'neutral'",
        "confidence": "REAL DEFAULT 0",
        "issue_tags": "TEXT DEFAULT '[]'",
        "is_risk": "INTEGER DEFAULT 0",
        "risk_reason": "TEXT",
        "reply_draft": "TEXT",
        "reply_status": "TEXT DEFAULT 'pending'",
        "posted_at": "TEXT",
        "collected_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    }
    for col, ddl in review_additions.items():
        if col not in review_columns:
            conn.execute(f"ALTER TABLE reviews ADD COLUMN {col} {ddl}")

    cs_additions = {
        "product_name": "TEXT",
        "customer_id": "TEXT",
        "title": "TEXT",
        "content": "TEXT",
        "inquiry_date": "TEXT",
        "item_id": "TEXT",
        "sentiment": "TEXT DEFAULT 'neutral'",
        "confidence": "REAL DEFAULT 0",
        "issue_tags": "TEXT DEFAULT '[]'",
        "is_risk": "INTEGER DEFAULT 0",
        "risk_reason": "TEXT",
        "reply_draft": "TEXT",
        "reply_status": "TEXT DEFAULT 'pending'",
        "posted_at": "TEXT",
        "collected_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    }
    for col, ddl in cs_additions.items():
        if col not in cs_columns:
            conn.execute(f"ALTER TABLE cs_items ADD COLUMN {col} {ddl}")

    alert_additions = {
        "channel": "TEXT",
        "item_type": "TEXT",
        "item_ref_id": "INTEGER",
        "message": "TEXT",
        "is_resolved": "INTEGER DEFAULT 0",
        "resolved_at": "TEXT",
    }
    for col, ddl in alert_additions.items():
        if col not in alert_columns:
            conn.execute(f"ALTER TABLE alerts ADD COLUMN {col} {ddl}")


# ── Upsert 저장 ───────────────────────────────────
def upsert_review(review: dict) -> bool:
    channel = review.get("channel", "")
    review_id = review.get("review_id_on_channel") or review.get("review_id")
    if not channel or not review_id or not review.get("content"):
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, content FROM reviews WHERE channel=? AND review_id_on_channel=?",
            (channel, review_id),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE reviews
                SET product_name=?, option_name=?, customer_id=?, order_number=?, rating=?,
                    content=?, review_date=?, updated_at=?
                WHERE channel=? AND review_id_on_channel=?
                """,
                (
                    review.get("product_name", ""),
                    review.get("option_name", ""),
                    review.get("customer_id", ""),
                    review.get("order_number", ""),
                    review.get("rating", 5),
                    review.get("content", ""),
                    review.get("review_date", ""),
                    now,
                    channel,
                    review_id,
                ),
            )
            return False

        conn.execute(
            """
            INSERT INTO reviews (
                channel, product_name, option_name, customer_id, order_number,
                rating, content, review_date, review_id_on_channel, collected_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel,
                review.get("product_name", ""),
                review.get("option_name", ""),
                review.get("customer_id", ""),
                review.get("order_number", ""),
                review.get("rating", 5),
                review.get("content", ""),
                review.get("review_date", ""),
                review_id,
                now,
                now,
                now,
            ),
        )
        return True


def upsert_cs(cs_item: dict) -> bool:
    channel = cs_item.get("channel", "")
    item_id = cs_item.get("item_id")
    if not channel or not item_id or not cs_item.get("content"):
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, content FROM cs_items WHERE channel=? AND item_id=?",
            (channel, item_id),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE cs_items
                SET product_name=?, customer_id=?, title=?, content=?, inquiry_date=?, updated_at=?
                WHERE channel=? AND item_id=?
                """,
                (
                    cs_item.get("product_name", ""),
                    cs_item.get("customer_id", ""),
                    cs_item.get("title", ""),
                    cs_item.get("content", ""),
                    cs_item.get("inquiry_date", ""),
                    now,
                    channel,
                    item_id,
                ),
            )
            return False

        conn.execute(
            """
            INSERT INTO cs_items (
                channel, product_name, customer_id, title, content,
                inquiry_date, item_id, collected_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel,
                cs_item.get("product_name", ""),
                cs_item.get("customer_id", ""),
                cs_item.get("title", ""),
                cs_item.get("content", ""),
                cs_item.get("inquiry_date", ""),
                item_id,
                now,
                now,
                now,
            ),
        )
        return True


# ── 조회 ─────────────────────────────────────────
def get_reviews(
    channel=None,
    status=None,
    collected_date=None,
    review_date=None,
    date_from=None,
    date_to=None,
    limit=200,
):
    query = """
        SELECT *
        FROM reviews
        WHERE 1=1
    """
    params = []

    if channel and channel != "전체":
        query += " AND channel = ?"
        params.append(channel)

    if status == "pending":
        query += " AND (reply_status IS NULL OR reply_status = 'pending')"
    elif status == "done":
        query += " AND reply_status = 'done'"

    if collected_date:
        query += " AND date(collected_at) = ?"
        params.append(collected_date)

    if review_date:
        query += " AND review_date = ?"
        params.append(review_date)

    if date_from:
        query += " AND review_date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND review_date <= ?"
        params.append(date_to)

    query += " ORDER BY review_date DESC, id DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_cs_items(channel: str = None, status: str = None,
                 collected_date: str = None,
                 limit: int = 200) -> list:
    wheres, params = [], []
    if channel:
        wheres.append("channel=?")
        params.append(channel)
    if status:
        wheres.append("reply_status=?")
        params.append(status)
    if collected_date:
        wheres.append("substr(collected_at, 1, 10)=?")
        params.append(collected_date)

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM cs_items {where_sql} ORDER BY collected_at DESC, inquiry_date DESC, id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    return [dict(r) for r in rows]


def get_review_by_id(review_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    return dict(row) if row else None


def get_cs_by_id(item_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM cs_items WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def get_collection_dates(table_name: str) -> list:
    if table_name not in {"reviews", "cs_items"}:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT substr(collected_at, 1, 10) AS d FROM {table_name} WHERE collected_at IS NOT NULL ORDER BY d DESC"
        ).fetchall()
    return [r["d"] for r in rows if r["d"]]


# ── 업데이트 ─────────────────────────────────────
def update_review_analysis(review_id: int, sentiment: str = None, confidence: float = None,
                           issue_tags=None, is_risk: int = None, risk_reason: str = None):
    fields, params = [], []
    if sentiment is not None:
        fields.append("sentiment=?")
        params.append(sentiment)
    if confidence is not None:
        fields.append("confidence=?")
        params.append(confidence)
    if issue_tags is not None:
        fields.append("issue_tags=?")
        params.append(json.dumps(issue_tags, ensure_ascii=False))
    if is_risk is not None:
        fields.append("is_risk=?")
        params.append(int(is_risk))
    if risk_reason is not None:
        fields.append("risk_reason=?")
        params.append(risk_reason)
    fields.append("updated_at=?")
    params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    params.append(review_id)

    with get_conn() as conn:
        conn.execute(f"UPDATE reviews SET {', '.join(fields)} WHERE id=?", params)


def update_cs_analysis(item_id: int, sentiment: str = None, confidence: float = None,
                       issue_tags=None, is_risk: int = None, risk_reason: str = None):
    fields, params = [], []
    if sentiment is not None:
        fields.append("sentiment=?")
        params.append(sentiment)
    if confidence is not None:
        fields.append("confidence=?")
        params.append(confidence)
    if issue_tags is not None:
        fields.append("issue_tags=?")
        params.append(json.dumps(issue_tags, ensure_ascii=False))
    if is_risk is not None:
        fields.append("is_risk=?")
        params.append(int(is_risk))
    if risk_reason is not None:
        fields.append("risk_reason=?")
        params.append(risk_reason)
    fields.append("updated_at=?")
    params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    params.append(item_id)

    with get_conn() as conn:
        conn.execute(f"UPDATE cs_items SET {', '.join(fields)} WHERE id=?", params)


def update_review_reply(review_id: int, reply_draft: str, reply_status: str = None):
    fields = ["reply_draft=?", "updated_at=?"]
    params = [reply_draft, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    if reply_status is not None:
        fields.insert(1, "reply_status=?")
        params.insert(1, reply_status)
    params.append(review_id)

    with get_conn() as conn:
        conn.execute(f"UPDATE reviews SET {', '.join(fields)} WHERE id=?", params)


def update_cs_reply(item_id: int, reply_draft: str, reply_status: str = None):
    fields = ["reply_draft=?", "updated_at=?"]
    params = [reply_draft, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    if reply_status is not None:
        fields.insert(1, "reply_status=?")
        params.insert(1, reply_status)
    params.append(item_id)

    with get_conn() as conn:
        conn.execute(f"UPDATE cs_items SET {', '.join(fields)} WHERE id=?", params)


def mark_review_posted(review_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "UPDATE reviews SET reply_status='posted', posted_at=?, updated_at=? WHERE id=?",
            (now, now, review_id),
        )


def mark_cs_posted(item_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "UPDATE cs_items SET reply_status='posted', posted_at=?, updated_at=? WHERE id=?",
            (now, now, item_id),
        )


# ── 삭제 / 초기화 ─────────────────────────────────
def delete_reviews(channel: str = None):
    with get_conn() as conn:
        if channel:
            conn.execute("DELETE FROM reviews WHERE channel=?", (channel,))
        else:
            conn.execute("DELETE FROM reviews")


def delete_cs_items(channel: str = None):
    with get_conn() as conn:
        if channel:
            conn.execute("DELETE FROM cs_items WHERE channel=?", (channel,))
        else:
            conn.execute("DELETE FROM cs_items")


def reset_reviews(channel: str = None):
    delete_reviews(channel=channel)


def reset_cs_items(channel: str = None):
    delete_cs_items(channel=channel)


def reset_reply_data(channel: str = None):
    delete_reviews(channel=channel)
    delete_cs_items(channel=channel)


def delete_review(review_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM reviews WHERE id=?", (review_id,))


def delete_cs_item(item_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM cs_items WHERE id=?", (item_id,))


# ── 알림 ─────────────────────────────────────────
def create_alert(level: str, message: str, channel: str = None,
                 item_type: str = None, item_ref_id: int = None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO alerts (level, channel, item_type, item_ref_id, message, is_resolved)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (level, channel, item_type, item_ref_id, message),
        )


def get_unresolved_alerts(limit: int = 20) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE is_resolved=0 ORDER BY CASE level WHEN 'critical' THEN 0 ELSE 1 END, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_alert(alert_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "UPDATE alerts SET is_resolved=1, resolved_at=? WHERE id=?",
            (now, alert_id),
        )


# ── 통계 / 리포트 ─────────────────────────────────
def get_review_stats(days_back: int = None):
    wheres, params = [], []
    if days_back:
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        wheres.append("review_date>=?")
        params.append(start_date)

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
                channel,
                COUNT(*) AS total,
                AVG(COALESCE(rating, 0)) AS avg_rating,
                SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) AS neg_count,
                SUM(CASE WHEN reply_status='pending' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN is_risk=1 THEN 1 ELSE 0 END) AS risk_count
            FROM reviews
            {where_sql}
            GROUP BY channel
            ORDER BY total DESC
            """,
            params,
        ).fetchall()

    result = {}
    for row in rows:
        result[row["channel"]] = {
            "total": row["total"] or 0,
            "avg_rating": row["avg_rating"] or 0,
            "neg_count": row["neg_count"] or 0,
            "pending_count": row["pending_count"] or 0,
            "risk_count": row["risk_count"] or 0,
        }
    return result


def get_claim_rates(min_reviews: int = 3):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                product_name,
                COALESCE(option_name, '') AS option_name,
                channel,
                COUNT(*) AS total_reviews,
                SUM(CASE WHEN sentiment='negative' OR is_risk=1 THEN 1 ELSE 0 END) AS negative_reviews,
                ROUND(
                    100.0 * SUM(CASE WHEN sentiment='negative' OR is_risk=1 THEN 1 ELSE 0 END) / COUNT(*),
                    1
                ) AS claim_rate
            FROM reviews
            WHERE COALESCE(product_name, '') <> ''
            GROUP BY product_name, COALESCE(option_name, ''), channel
            HAVING COUNT(*) >= ?
            ORDER BY claim_rate DESC, total_reviews DESC
            """,
            (min_reviews,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── 배치 대상 조회 ─────────────────────────────────
def get_pending_review_ids(channel: str = None, limit: int = 50) -> list:
    wheres = ["reply_status='pending'", "(reply_draft IS NULL OR reply_draft='')"]
    params = []
    if channel:
        wheres.append("channel=?")
        params.append(channel)

    where_sql = " AND ".join(wheres)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id FROM reviews WHERE {where_sql} ORDER BY id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    return [r["id"] for r in rows]


def get_pending_cs_ids(channel: str = None, limit: int = 50) -> list:
    wheres = ["reply_status='pending'", "(reply_draft IS NULL OR reply_draft='')"]
    params = []
    if channel:
        wheres.append("channel=?")
        params.append(channel)

    where_sql = " AND ".join(wheres)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id FROM cs_items WHERE {where_sql} ORDER BY id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    return [r["id"] for r in rows]


def check_and_create_alerts():
    alerts_created = 0

    with get_conn() as conn:
        # 위험 리뷰 중 미해결 알림이 없는 것 생성
        risky_reviews = conn.execute(
            """
            SELECT id, channel, product_name, content, risk_reason
            FROM reviews
            WHERE is_risk=1
              AND id NOT IN (
                  SELECT item_ref_id FROM alerts
                  WHERE item_type='review' AND is_resolved=0
              )
            ORDER BY id DESC
            """
        ).fetchall()

        for row in risky_reviews:
            message = f"[리뷰 위험] {row['channel']} / {row['product_name'] or '상품'} / {row['risk_reason'] or '위험 감지'}"
            conn.execute(
                """
                INSERT INTO alerts (level, channel, item_type, item_ref_id, message, is_resolved)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                ("critical", row["channel"], "review", row["id"], message),
            )
            alerts_created += 1

        # 위험 CS 중 미해결 알림이 없는 것 생성
        risky_cs = conn.execute(
            """
            SELECT id, channel, product_name, title, risk_reason
            FROM cs_items
            WHERE is_risk=1
              AND id NOT IN (
                  SELECT item_ref_id FROM alerts
                  WHERE item_type='cs' AND is_resolved=0
              )
            ORDER BY id DESC
            """
        ).fetchall()

        for row in risky_cs:
            message = f"[CS 위험] {row['channel']} / {row['product_name'] or row['title'] or '문의'} / {row['risk_reason'] or '위험 감지'}"
            conn.execute(
                """
                INSERT INTO alerts (level, channel, item_type, item_ref_id, message, is_resolved)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                ("critical", row["channel"], "cs", row["id"], message),
            )
            alerts_created += 1

    return {"created": alerts_created}

def get_review_dates(channel=None):
    query = """
        SELECT DISTINCT review_date
        FROM reviews
        WHERE review_date IS NOT NULL
          AND review_date != ''
    """
    params = []

    if channel and channel != "전체":
        query += " AND channel = ?"
        params.append(channel)

    query += " ORDER BY review_date DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [row["review_date"] for row in rows]

def get_collected_dates(channel=None):
    query = """
        SELECT DISTINCT date(collected_at) as collected_date
        FROM reviews
        WHERE collected_at IS NOT NULL
    """
    params = []

    if channel and channel != "전체":
        query += " AND channel = ?"
        params.append(channel)

    query += " ORDER BY collected_date DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [row["collected_date"] for row in rows]

init_db()
