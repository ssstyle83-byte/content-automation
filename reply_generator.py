"""
Claude 기반 리뷰/CS 답변 자동 생성 모듈
"""
import json
import re
import os
from anthropic import Anthropic
from dotenv import load_dotenv
import db

load_dotenv()

PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "review_prompts.json")


def _get_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return Anthropic(api_key=api_key)


def _load_templates() -> dict:
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def generate_reply(review: dict) -> str:
    """
    리뷰 데이터를 기반으로 맞춤 답변 생성.
    review: DB에서 가져온 reviews 테이블 dict
    """
    templates = _load_templates()
    issue_tags = []
    try:
        issue_tags = json.loads(review.get("issue_tags") or "[]")
    except Exception:
        pass

    sentiment = review.get("sentiment", "neutral")
    rating = review.get("rating", 0)
    product_name = review.get("product_name") or "상품"
    option_name = review.get("option_name") or ""
    channel = review.get("channel") or ""
    content = review.get("content") or ""
    customer_id = review.get("customer_id") or ""

    # 고객 호칭 생성
    if customer_id and len(customer_id) > 2:
        customer_name = customer_id[:2] + "**님"
    else:
        customer_name = "고객님"

    client = _get_client()

    # 이슈별 힌트 템플릿 선택
    hint_template = ""
    for tag in issue_tags:
        if tag in templates:
            hint_template = templates[tag]
            break
    if not hint_template:
        hint_template = templates.get("기본_긍정" if sentiment == "positive" else "기본_부정", "")

    product_full = f"{product_name}" + (f" ({option_name})" if option_name else "")

    prompt = f"""다음 쇼핑몰 리뷰에 대한 판매자 답변을 작성해주세요.

[리뷰 정보]
- 채널: {channel}
- 상품: {product_full}
- 평점: {rating}점
- 감정: {sentiment}
- 이슈 유형: {', '.join(issue_tags) if issue_tags else '없음'}
- 리뷰 내용: {content}
- 고객 호칭: {customer_name}

[답변 작성 지침]
1. {customer_name}으로 시작
2. 리뷰 내용을 반영한 맞춤 답변 (복붙 느낌 X)
3. 200자 이내로 간결하게
4. 부정 리뷰는 진심 어린 사과 + 개선 의지 표현
5. 긍정 리뷰는 감사 인사 + 재구매 유도
6. 자연스럽고 따뜻한 한국어

[참고 템플릿]
{hint_template}

답변만 출력 (설명 없이):"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        reply = msg.content[0].text.strip()
        # 따옴표 제거
        reply = re.sub(r'^["\']+|["\']+$', '', reply)
        return reply
    except Exception as e:
        print(f"[ReplyGen] 답변 생성 오류: {e}")
        # 폴백: 템플릿 기반 답변
        return _template_fallback(hint_template, customer_name, product_full, issue_tags)


def _template_fallback(template: str, customer_name: str,
                       product_name: str, issue_tags: list) -> str:
    """API 실패 시 템플릿 치환 폴백."""
    if not template:
        return f"{customer_name}, 소중한 리뷰 감사합니다. 더 좋은 서비스로 보답하겠습니다."
    issue_text = ", ".join(issue_tags) if issue_tags else "불편하신 점"
    return (template
            .replace("{고객호칭}", customer_name)
            .replace("{상품명}", product_name)
            .replace("{이슈내용}", issue_text))


def generate_cs_reply(cs_item: dict) -> str:
    """CS 문의에 대한 답변 생성."""
    templates = _load_templates()
    title = cs_item.get("title") or ""
    content = cs_item.get("content") or ""
    product_name = cs_item.get("product_name") or "상품"
    channel = cs_item.get("channel") or ""
    issue_tags = []
    try:
        issue_tags = json.loads(cs_item.get("issue_tags") or "[]")
    except Exception:
        pass

    # CS 관련 힌트 템플릿
    hint_template = ""
    for tag in issue_tags:
        cs_key = f"cs_{tag.replace('문의', '문의')}"
        if cs_key in templates:
            hint_template = templates[cs_key]
            break

    client = _get_client()
    prompt = f"""다음 쇼핑몰 고객 문의에 대한 판매자 답변을 작성해주세요.

[문의 정보]
- 채널: {channel}
- 상품: {product_name}
- 문의 제목: {title}
- 문의 내용: {content}
- 이슈 유형: {', '.join(issue_tags) if issue_tags else '일반 문의'}

[답변 작성 지침]
1. "안녕하세요!" 로 시작
2. 문의 내용에 직접 답변
3. 150자 이내로 간결하게
4. 친절하고 전문적인 한국어

답변만 출력:"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[ReplyGen] CS 답변 생성 오류: {e}")
        return f"안녕하세요! 문의 주셔서 감사합니다. 해당 내용을 확인 후 빠른 시간 내에 답변 드리겠습니다."


def generate_replies_batch(review_ids: list[int], progress_callback=None) -> dict:
    """
    미생성 리뷰 답변 일괄 생성 후 DB 저장.
    is_risk=True 항목은 'review_needed' 상태로 저장 (자동 등록 제외).
    """
    generated = 0
    errors = 0
    total = len(review_ids)

    with db.get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM reviews WHERE id IN ({','.join('?' * len(review_ids))})",
            review_ids
        ).fetchall()
    reviews = [dict(r) for r in rows]

    for i, review in enumerate(reviews):
        try:
            draft = generate_reply(review)
            # 위험 리뷰는 검토 필요 상태로 저장
            status = "review_needed" if review.get("is_risk") else "pending"
            db.update_review_reply(review["id"], draft, status)
            generated += 1
        except Exception as e:
            print(f"[ReplyGen] 리뷰 {review.get('id')} 답변 생성 오류: {e}")
            errors += 1

        if progress_callback:
            progress_callback(i + 1, total)

    return {"generated": generated, "errors": errors}


def generate_cs_replies_batch(cs_ids: list[int], progress_callback=None) -> dict:
    """CS 문의 답변 일괄 생성."""
    generated = 0
    errors = 0
    total = len(cs_ids)

    with db.get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM cs_items WHERE id IN ({','.join('?' * len(cs_ids))})",
            cs_ids
        ).fetchall()
    items = [dict(r) for r in rows]

    for i, item in enumerate(items):
        try:
            draft = generate_cs_reply(item)
            status = "review_needed" if item.get("is_risk") else "pending"
            db.update_cs_reply(item["id"], draft, status)
            generated += 1
        except Exception as e:
            print(f"[ReplyGen] CS {item.get('id')} 답변 생성 오류: {e}")
            errors += 1

        if progress_callback:
            progress_callback(i + 1, total)

    return {"generated": generated, "errors": errors}
