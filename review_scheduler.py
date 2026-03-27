"""
CS/리뷰 자동 수집 스케줄러
별도 터미널에서 실행: python review_scheduler.py

매일 지정 시각에:
1. 전체 채널 리뷰/CS 수집
2. 감정 분석 + 이슈 태깅
3. 답변 초안 자동 생성
4. pending 항목 자동 등록
"""
import time
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

REVIEW_SCHEDULE_FILE = "review_schedule_config.json"
DEFAULT_CONFIG = {
    "hour": 9,
    "minute": 0,
    "channels": ["스마트스토어"],
    "days_back": 1,
    "do_analyze": True,
    "do_generate_reply": True,
    "do_auto_post": True,
    "active": True
}


def load_config() -> dict:
    if os.path.exists(REVIEW_SCHEDULE_FILE):
        try:
            with open(REVIEW_SCHEDULE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    with open(REVIEW_SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def run_pipeline(config: dict):
    """전체 수집 → 분석 → 답변 생성 → 자동 등록 파이프라인."""
    from crawlers import CRAWLERS
    import db
    import analyzer
    import reply_generator
    import auto_poster

    channels = config.get("channels", ["스마트스토어"])
    days_back = config.get("days_back", 1)
    do_analyze = config.get("do_analyze", True)
    do_generate = config.get("do_generate_reply", True)
    do_post = config.get("do_auto_post", True)

    log(f"=== 자동 수집 시작: {channels} / {days_back}일치 ===")

    for channel in channels:
        crawler_cls = CRAWLERS.get(channel)
        if not crawler_cls:
            log(f"[{channel}] 크롤러 없음, 건너뜀")
            continue

        try:
            log(f"[{channel}] 수집 시작...")
            crawler = crawler_cls(headless=True)
            result = crawler.run_collect(days_back=days_back)

            if result.get("error"):
                log(f"[{channel}] 수집 오류: {result['error']}")
                continue

            # DB 저장
            new_review_ids = []
            for rv in result.get("reviews", []):
                rid = db.upsert_review(rv)
                if rid:
                    new_review_ids.append(rid)

            new_cs_ids = []
            for cs in result.get("cs", []):
                cid = db.upsert_cs(cs)
                if cid:
                    new_cs_ids.append(cid)

            log(f"[{channel}] 신규 리뷰 {len(new_review_ids)}건, CS {len(new_cs_ids)}건")

            # 감정 분석
            if do_analyze:
                with db.get_conn() as conn:
                    unanalyzed = conn.execute(
                        "SELECT id FROM reviews WHERE channel=? AND sentiment='neutral' ORDER BY id DESC LIMIT 100",
                        (channel,)
                    ).fetchall()
                ids = [r["id"] for r in unanalyzed]
                if ids:
                    a_result = analyzer.analyze_batch(ids)
                    log(f"[{channel}] 분석 완료: {a_result['processed']}건")

                with db.get_conn() as conn:
                    cs_unanalyzed = conn.execute(
                        "SELECT id FROM cs_items WHERE channel=? AND sentiment='neutral' ORDER BY id DESC LIMIT 50",
                        (channel,)
                    ).fetchall()
                cs_ids = [r["id"] for r in cs_unanalyzed]
                if cs_ids:
                    analyzer.analyze_cs_batch(cs_ids)

            # 답변 생성
            if do_generate:
                with db.get_conn() as conn:
                    no_reply = conn.execute(
                        "SELECT id FROM reviews WHERE channel=? AND reply_draft IS NULL ORDER BY id DESC LIMIT 50",
                        (channel,)
                    ).fetchall()
                ids = [r["id"] for r in no_reply]
                if ids:
                    r_result = reply_generator.generate_replies_batch(ids)
                    log(f"[{channel}] 답변 생성: {r_result['generated']}건")

                with db.get_conn() as conn:
                    cs_no_reply = conn.execute(
                        "SELECT id FROM cs_items WHERE channel=? AND reply_draft IS NULL ORDER BY id DESC LIMIT 50",
                        (channel,)
                    ).fetchall()
                cs_ids = [r["id"] for r in cs_no_reply]
                if cs_ids:
                    reply_generator.generate_cs_replies_batch(cs_ids)

            # 자동 등록
            if do_post:
                p_result = auto_poster.post_review_replies(channel=channel)
                log(f"[{channel}] 리뷰 자동 등록: {p_result['posted']}건 성공 / {p_result['failed']}건 실패")

                c_result = auto_poster.post_cs_replies(channel=channel)
                log(f"[{channel}] CS 자동 등록: {c_result['posted']}건 성공 / {c_result['failed']}건 실패")

        except Exception as e:
            log(f"[{channel}] 파이프라인 오류: {e}")

    log("=== 자동 수집 완료 ===")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    # 로그 파일에도 기록
    try:
        with open("review_scheduler.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    log("리뷰 스케줄러 시작")
    last_run_date = None

    while True:
        config = load_config()

        if not config.get("active", True):
            time.sleep(30)
            continue

        now = datetime.now()
        scheduled_hour = config.get("hour", 9)
        scheduled_minute = config.get("minute", 0)
        today = now.strftime("%Y-%m-%d")

        # 지정 시각 도달 + 오늘 미실행
        if (now.hour == scheduled_hour and
                now.minute == scheduled_minute and
                last_run_date != today):
            try:
                run_pipeline(config)
                last_run_date = today
            except Exception as e:
                log(f"파이프라인 실행 오류: {e}")

        time.sleep(20)  # 20초마다 체크


if __name__ == "__main__":
    # 즉시 실행 옵션 (--now 인자)
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        log("즉시 실행 모드")
        config = load_config()
        run_pipeline(config)
    else:
        main()
