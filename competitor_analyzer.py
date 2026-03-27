"""
리뷰 키워드 분석 + 경쟁사 비교표 생성
Claude API 활용
"""

import os
import json
from collections import Counter
from anthropic import Anthropic

client = Anthropic()


def analyze_reviews_with_claude(competitor_name: str, reviews: list) -> dict:
    """Claude API로 리뷰 키워드 분석"""
    if not reviews:
        return {"keywords": [], "strengths": [], "weaknesses": [], "summary": "리뷰 없음"}

    reviews_text = "\n".join([f"- {r}" for r in reviews[:20]])

    prompt = f"""다음은 '{competitor_name}' 제품의 고객 리뷰입니다.

{reviews_text}

아래 형식의 JSON으로 분석해주세요. JSON만 출력하고 다른 텍스트는 쓰지 마세요:
{{
    "keywords": ["빈도 높은 키워드 10개"],
    "strengths": ["경쟁사 강점 3-5개"],
    "weaknesses": ["경쟁사 약점 3-5개"],
    "summary": "전체 리뷰 한줄 요약",
    "sentiment": "긍정/부정/혼재"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        # JSON 파싱
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Claude] 리뷰 분석 오류: {e}")
        return {
            "keywords": simple_keyword_count(reviews),
            "strengths": [],
            "weaknesses": [],
            "summary": "분석 실패",
            "sentiment": "알 수 없음"
        }


def simple_keyword_count(reviews: list) -> list:
    """단순 키워드 빈도 계산 (Claude API 없을 때)"""
    stopwords = {"이", "가", "을", "를", "은", "는", "에", "의", "도", "로", "와", "과", "한", "하다", "있다", "되다"}
    words = []
    for review in reviews:
        words.extend([w for w in review.split() if len(w) > 1 and w not in stopwords])
    counter = Counter(words)
    return [word for word, _ in counter.most_common(10)]


def generate_comparison_table(my_products: list, competitor_data: dict) -> str:
    """우리 상품 vs 경쟁사 비교표 생성"""
    if not competitor_data:
        return "비교 데이터 없음"

    # 경쟁사 상품 정보 정리
    comp_summary = {}
    for name, data in competitor_data.items():
        products = data.get("products", []) or data.get("best_products", [])
        prices = [p.get("price", 0) for p in products if p.get("price", 0) > 0]
        comp_summary[name] = {
            "avg_price": int(sum(prices) / len(prices)) if prices else 0,
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
            "product_count": len(products),
            "strengths": data.get("analysis", {}).get("strengths", []),
            "weaknesses": data.get("analysis", {}).get("weaknesses", []),
        }

    prompt = f"""우리 상품과 경쟁사 데이터를 바탕으로 비교 분석표를 만들어주세요.

우리 상품:
{json.dumps(my_products, ensure_ascii=False, indent=2)}

경쟁사 데이터:
{json.dumps(comp_summary, ensure_ascii=False, indent=2)}

다음 형식으로 마크다운 표를 포함한 분석 리포트를 작성해주세요:
1. 가격 포지셔닝 비교표
2. 경쟁사별 강점/약점 요약
3. 우리 상품 대비 전략적 시사점 3가지"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"비교표 생성 실패: {e}"


def full_analysis(crawler_results: dict, my_products: list = None) -> dict:
    """전체 분석 파이프라인"""
    analysis_results = {}

    for name, data in crawler_results.items():
        if "error" in data:
            continue

        print(f"[분석] {name} 리뷰 분석 중...")
        reviews = data.get("reviews_summary", [])
        analysis = analyze_reviews_with_claude(name, reviews)
        data["analysis"] = analysis
        analysis_results[name] = data

    # 비교표 생성
    comparison = ""
    if my_products:
        print("[분석] 경쟁사 비교표 생성 중...")
        comparison = generate_comparison_table(my_products, analysis_results)

    return {
        "competitors": analysis_results,
        "comparison_table": comparison,
        "generated_at": __import__("datetime").datetime.now().isoformat()
    }
