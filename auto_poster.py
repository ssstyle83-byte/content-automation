"""
각 채널에 답변을 자동으로 등록하는 모듈.
is_risk=False + reply_status='pending' 항목만 처리.
"""
import os
from dotenv import load_dotenv
import db

load_dotenv()


def _get_crawler(channel: str):
    """채널명으로 크롤러 인스턴스 반환."""
    from crawlers import CRAWLERS
    cls = CRAWLERS.get(channel)
    if not cls:
        return None
    return cls(headless=True)


def post_review_replies(channel: str = None, limit: int = 50) -> dict:
    """
    pending 상태의 리뷰 답변을 자동 등록.
    is_risk=True 항목은 절대 자동 등록하지 않음.
    """
    posted = 0
    failed = 0
    skipped = 0

    # 채널별 처리
    channels_to_process = [channel] if channel else _get_active_channels("reviews")

    for ch in channels_to_process:
        crawler = _get_crawler(ch)
        if not crawler:
            print(f"[AutoPoster] '{ch}' 크롤러 없음, 건너뜀")
            skipped += 1
            continue

        # pending + not risk 리뷰 조회
        with db.get_conn() as conn:
            rows = conn.execute("""
                SELECT id, reply_draft, order_number, review_date
                FROM reviews
                WHERE channel=? AND reply_status='pending' AND is_risk=0
                  AND reply_draft IS NOT NULL AND reply_draft != ''
                ORDER BY review_date DESC
                LIMIT ?
            """, (ch, limit)).fetchall()

        if not rows:
            continue

        with crawler:
            if not crawler.login():
                print(f"[AutoPoster] [{ch}] 로그인 실패")
                failed += len(rows)
                continue

            for row in rows:
                review_id = row["id"]
                draft = row["reply_draft"]
                order_number = row["order_number"] or str(review_id)

                try:
                    success = crawler.post_review_reply(order_number, draft)
                    if success:
                        db.mark_review_posted(review_id)
                        posted += 1
                        print(f"[AutoPoster] [{ch}] 리뷰 {review_id} 답변 등록 완료")
                    else:
                        failed += 1
                        print(f"[AutoPoster] [{ch}] 리뷰 {review_id} 답변 등록 실패")
                except Exception as e:
                    failed += 1
                    print(f"[AutoPoster] [{ch}] 리뷰 {review_id} 오류: {e}")

    return {"posted": posted, "failed": failed, "skipped": skipped}


def post_cs_replies(channel: str = None, limit: int = 50) -> dict:
    """pending 상태의 CS 답변을 자동 등록."""
    posted = 0
    failed = 0
    skipped = 0

    channels_to_process = [channel] if channel else _get_active_channels("cs")

    for ch in channels_to_process:
        crawler = _get_crawler(ch)
        if not crawler:
            skipped += 1
            continue

        with db.get_conn() as conn:
            rows = conn.execute("""
                SELECT id, reply_draft, item_id
                FROM cs_items
                WHERE channel=? AND reply_status='pending' AND is_risk=0
                  AND reply_draft IS NOT NULL AND reply_draft != ''
                ORDER BY inquiry_date DESC
                LIMIT ?
            """, (ch, limit)).fetchall()

        if not rows:
            continue

        with crawler:
            if not crawler.login():
                failed += len(rows)
                continue

            for row in rows:
                cs_id = row["id"]
                draft = row["reply_draft"]
                item_id = row["item_id"] or str(cs_id)

                try:
                    success = crawler.post_cs_reply(item_id, draft)
                    if success:
                        db.mark_cs_posted(cs_id)
                        posted += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    print(f"[AutoPoster] [{ch}] CS {cs_id} 오류: {e}")

    return {"posted": posted, "failed": failed, "skipped": skipped}


def post_single_review_reply(review_id: int) -> bool:
    """단건 리뷰 답변 등록 (탭 8 수동 등록용)."""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM reviews WHERE id=?", (review_id,)
        ).fetchone()
    if not row:
        return False

    review = dict(row)
    channel = review["channel"]
    draft = review.get("reply_draft") or ""
    order_number = review.get("order_number") or str(review_id)

    if not draft:
        return False

    crawler = _get_crawler(channel)
    if not crawler:
        return False

    with crawler:
        if not crawler.login():
            return False
        success = crawler.post_review_reply(order_number, draft)
        if success:
            db.mark_review_posted(review_id)
        return success


def post_single_cs_reply(cs_id: int) -> bool:
    """단건 CS 답변 등록."""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM cs_items WHERE id=?", (cs_id,)
        ).fetchone()
    if not row:
        return False

    item = dict(row)
    channel = item["channel"]
    draft = item.get("reply_draft") or ""
    item_id = item.get("item_id") or str(cs_id)

    if not draft:
        return False

    crawler = _get_crawler(channel)
    if not crawler:
        return False

    with crawler:
        if not crawler.login():
            return False
        success = crawler.post_cs_reply(item_id, draft)
        if success:
            db.mark_cs_posted(cs_id)
        return success


def _get_active_channels(table: str) -> list[str]:
    """DB에 데이터가 있는 채널 목록 반환."""
    tbl = "reviews" if table == "reviews" else "cs_items"
    with db.get_conn() as conn:
        rows = conn.execute(f"SELECT DISTINCT channel FROM {tbl}").fetchall()
    return [r["channel"] for r in rows]
