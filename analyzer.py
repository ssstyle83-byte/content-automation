"""
Claude 기반 감정 분석 + 이슈 태깅 모듈
리뷰/CS 텍스트를 분석하여 감정, 이슈 유형, 위험 여부를 판별합니다.
"""
import json
import re
import os
from anthropic import Anthropic
from dotenv import load_dotenv
import db

load_dotenv()

ISSUE_TAGS = ["배송지연", "배송파손", "사이즈오류", "품질불량", "색상차이", "포장불량",
              "오배송", "환불요청", "교환요청", "사용법문의", "재입고문의", "기타"]

RISK_KEYWORDS = ["환불", "신고", "고발", "소비자원", "공정위", "사기", "불량품", "폐기",
                 "쓰레기", "최악", "별점테러", "법적조치", "변호사"]


def _get_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return Anthropic(api_key=api_key)


def analyze_review(content: str) -> dict:
    """
    단일 리뷰 텍스트 분석.
    반환: {sentiment, issue_tags, is_risk, risk_reason, score}
    """
    # 빠른 위험 키워드 사전 검사
    pre_risk = any(kw in content for kw in RISK_KEYWORDS)

    client = _get_client()
    prompt = f"""다음 쇼핑몰 리뷰를 분석하여 반드시 JSON만 출력하세요. 설명 없이 JSON만.

리뷰 내용:
{content}

분석 기준:
- sentiment: "positive"(긍정), "negative"(부정), "neutral"(중립)
- issue_tags: 해당되는 항목만 배열로 [{', '.join(ISSUE_TAGS)}]
- is_risk: 환불요구/신고언급/강한욕설/소비자분쟁 시 true
- risk_reason: is_risk가 true일 때 이유 (없으면 null)
- score: 0~100 (100=매우긍정)

출력 형식:
{{
  "sentiment": "negative",
  "issue_tags": ["배송지연", "품질불량"],
  "is_risk": false,
  "risk_reason": null,
  "score": 20
}}"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            # 사전 위험 검사 결과 반영
            if pre_risk and not result.get("is_risk"):
                result["is_risk"] = True
                result["risk_reason"] = "위험 키워드 감지"
            return result
    except Exception as e:
        print(f"[Analyzer] 분석 오류: {e}")

    # 폴백: 키워드 기반 간단 분석
    return _keyword_fallback(content, pre_risk)


def _keyword_fallback(content: str, pre_risk: bool) -> dict:
    """API 실패 시 키워드 기반 폴백 분석."""
    negative_words = ["불량", "파손", "오배송", "늦음", "최악", "별로", "실망",
                      "환불", "교환", "문제", "하자", "잘못", "안와", "안옴"]
    positive_words = ["좋아요", "만족", "추천", "예뻐요", "빨라요", "완벽", "최고",
                      "감사", "재구매", "굿", "좋습니다"]

    neg_score = sum(1 for w in negative_words if w in content)
    pos_score = sum(1 for w in positive_words if w in content)

    if neg_score > pos_score:
        sentiment = "negative"
        score = max(10, 40 - neg_score * 5)
    elif pos_score > neg_score:
        sentiment = "positive"
        score = min(95, 70 + pos_score * 5)
    else:
        sentiment = "neutral"
        score = 50

    tags = [t for t in ISSUE_TAGS if t in content]

    return {
        "sentiment": sentiment,
        "issue_tags": tags,
        "is_risk": pre_risk,
        "risk_reason": "위험 키워드 감지" if pre_risk else None,
        "score": score
    }


def analyze_batch(review_ids: list[int], progress_callback=None) -> dict:
    """
    DB에서 미분석 리뷰를 일괄 분석.
    progress_callback(current, total) 형태로 진행률 콜백 가능.
    반환: {processed: int, errors: int}
    """
    processed = 0
    errors = 0
    total = len(review_ids)

    for i, review_id in enumerate(review_ids):
        try:
            # DB에서 리뷰 내용 가져오기
            with db.get_conn() as conn:
                row = conn.execute(
                    "SELECT content FROM reviews WHERE id=?", (review_id,)
                ).fetchone()
            if not row or not row["content"]:
                continue

            result = analyze_review(row["content"])
            db.update_review_analysis(
                review_id,
                sentiment=result.get("sentiment", "neutral"),
                issue_tags=result.get("issue_tags", []),
                is_risk=result.get("is_risk", False),
                risk_reason=result.get("risk_reason")
            )
            processed += 1
        except Exception as e:
            print(f"[Analyzer] 리뷰 {review_id} 분석 오류: {e}")
            errors += 1

        if progress_callback:
            progress_callback(i + 1, total)

    # 분석 후 알림 체크
    db.check_and_create_alerts()

    return {"processed": processed, "errors": errors}


def analyze_cs_batch(cs_ids: list[int], progress_callback=None) -> dict:
    """CS 문의 일괄 분석."""
    processed = 0
    errors = 0
    total = len(cs_ids)

    for i, cs_id in enumerate(cs_ids):
        try:
            with db.get_conn() as conn:
                row = conn.execute(
                    "SELECT content, title FROM cs_items WHERE id=?", (cs_id,)
                ).fetchone()
            if not row:
                continue

            text = (row["content"] or "") + " " + (row["title"] or "")
            result = analyze_review(text)  # 동일 분석 로직 재사용

            with db.get_conn() as conn:
                conn.execute(
                    """UPDATE cs_items SET sentiment=?, issue_tags=?, is_risk=?, risk_reason=?
                       WHERE id=?""",
                    (result.get("sentiment", "neutral"),
                     json.dumps(result.get("issue_tags", []), ensure_ascii=False),
                     1 if result.get("is_risk") else 0,
                     result.get("risk_reason"),
                     cs_id)
                )
            processed += 1
        except Exception as e:
            print(f"[Analyzer] CS {cs_id} 분석 오류: {e}")
            errors += 1

        if progress_callback:
            progress_callback(i + 1, total)

    return {"processed": processed, "errors": errors}


def get_issue_summary(days_back: int = 30) -> dict:
    """
    기간별 이슈 태그 빈도 집계.
    반환: {tag: count, ...}
    """
    from datetime import datetime, timedelta
    since = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT issue_tags FROM reviews WHERE review_date >= ? AND issue_tags != '[]'",
            (since,)
        ).fetchall()

    tag_counts = {}
    for row in rows:
        try:
            tags = json.loads(row["issue_tags"])
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except Exception:
            pass

    return dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True))


def get_sentiment_trend(days_back: int = 30) -> list:
    """
    일별 감정 분포 집계.
    반환: [{date, positive, negative, neutral}, ...]
    """
    from datetime import datetime, timedelta
    since = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT review_date,
                   SUM(CASE WHEN sentiment='positive' THEN 1 ELSE 0 END) AS positive,
                   SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) AS negative,
                   SUM(CASE WHEN sentiment='neutral' THEN 1 ELSE 0 END) AS neutral
            FROM reviews
            WHERE review_date >= ?
            GROUP BY review_date
            ORDER BY review_date
        """, (since,)).fetchall()

    return [dict(r) for r in rows]
