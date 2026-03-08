"""
경쟁사 분석 크롤러
네이버 쇼핑 API + Playwright 기반
"""

import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# ← 핵심: .env 파일 로드
load_dotenv()

# 네이버 쇼핑 검색 API 설정
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
NAVER_SHOP_API = "https://openapi.naver.com/v1/search/shop.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 경쟁사 정보
COMPETITORS = {
    "닥터파이토": {
        "url": "https://brand.naver.com/dr_phyto",
        "search_keyword": "닥터파이토",
        "type": "brand"
    },
    "파이토뉴트리": {
        "url": "https://smartstore.naver.com/phytonutri",
        "search_keyword": "파이토뉴트리",
        "type": "smartstore"
    },
    "닥터린": {
        "url": "https://brand.naver.com/dr_lean",
        "search_keyword": "닥터린",
        "type": "brand"
    },
    "뉴트리모어": {
        "url": "https://brand.naver.com/nutrimore",
        "search_keyword": "뉴트리모어",
        "type": "brand"
    },
}


# ──────────────────────────────────────────
# 1. 네이버 쇼핑 API (가격/상품 기본정보)
# ──────────────────────────────────────────
def search_naver_shopping(keyword: str, display: int = 20) -> list:
    """네이버 쇼핑 API로 상품 검색"""
    if not NAVER_CLIENT_ID:
        print("[API] 네이버 API 키 없음 → Playwright 방식으로 대체")
        return []

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query": keyword,
        "display": display,
        "sort": "sim"
    }

    try:
        resp = requests.get(NAVER_SHOP_API, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])

        results = []
        for item in items:
            results.append({
                "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                "price": int(item.get("lprice", 0)),
                "mall": item.get("mallName", ""),
                "link": item.get("link", ""),
                "image": item.get("image", ""),
                "category": item.get("category1", ""),
                "product_id": item.get("productId", ""),
                "collected_at": datetime.now().isoformat()
            })
        return results
    except Exception as e:
        print(f"[API] 네이버 쇼핑 API 오류: {e}")
        return []


# ──────────────────────────────────────────
# 2. 리뷰 수집 (네이버 쇼핑 카탈로그 페이지)
# ──────────────────────────────────────────
def get_reviews_from_shopping(product_id: str, headless: bool = True) -> list:
    """네이버 쇼핑 카탈로그 페이지에서 리뷰 수집"""
    if not product_id:
        return []

    url = f"https://search.shopping.naver.com/catalog/{product_id}"
    reviews = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=HEADERS["User-Agent"]
            )
            page = context.new_page()

            print(f"  [리뷰] 페이지 접속 중...")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # 리뷰 탭 클릭 시도
            for sel in ["a:has-text('리뷰')", "button:has-text('리뷰')", "li:has-text('리뷰') a"]:
                try:
                    page.click(sel, timeout=3000)
                    time.sleep(2)
                    break
                except Exception:
                    continue

            # 리뷰 텍스트 셀렉터
            review_selectors = [
                "p.reviewContent__reviewText__t3HCd",
                "p.reviewContent__text",
                "[class*='reviewText']",
                "[class*='review_text']",
                "[class*='ReviewText']",
                "div[class*='review'] p",
            ]

            for sel in review_selectors:
                try:
                    items = page.locator(sel).all()
                    if items:
                        for item in items[:20]:
                            try:
                                text = item.inner_text().strip()
                                if text and len(text) > 10:
                                    reviews.append(text)
                            except Exception:
                                continue
                        if reviews:
                            print(f"  [리뷰] {len(reviews)}개 수집 완료")
                            break
                except Exception:
                    continue

            browser.close()

    except Exception as e:
        print(f"  [리뷰] 수집 실패: {e}")

    return reviews[:20]


def get_reviews_for_competitor(competitor_name: str, best_products: list, headless: bool = True) -> list:
    """경쟁사 베스트 상품에서 리뷰 수집"""
    for product in best_products[:3]:
        product_id = product.get("product_id", "")
        link = product.get("link", "")

        # product_id 직접 사용
        if product_id:
            print(f"  [리뷰] {competitor_name} - {product.get('title', '')[:30]} 리뷰 수집 중...")
            reviews = get_reviews_from_shopping(product_id, headless=headless)
            if reviews:
                return reviews

        # link에서 catalog ID 추출
        if "catalog" in link:
            try:
                catalog_id = link.split("catalog/")[1].split("?")[0]
                reviews = get_reviews_from_shopping(catalog_id, headless=headless)
                if reviews:
                    return reviews
            except Exception:
                continue

    return []


# ──────────────────────────────────────────
# 3. Playwright 크롤러 (메인)
# ──────────────────────────────────────────
class CompetitorCrawler:
    def __init__(self, headless: bool = True):
        self.headless = headless

    def crawl_all(self) -> dict:
        """전체 경쟁사 크롤링"""
        results = {}
        for name, info in COMPETITORS.items():
            print(f"\n[크롤링] {name} 시작...")
            try:
                data = self.crawl_one(name, info)
                results[name] = data
                print(f"[크롤링] {name} 완료: 상품 {len(data.get('best_products', []))}개, 리뷰 {len(data.get('reviews_summary', []))}개")
            except Exception as e:
                print(f"[크롤링] {name} 실패: {e}")
                results[name] = {"error": str(e)}
            time.sleep(2)
        return results

    def crawl_one(self, name: str, info: dict) -> dict:
        """단일 경쟁사 크롤링"""
        result = {
            "name": name,
            "url": info["url"],
            "collected_at": datetime.now().isoformat(),
            "products": [],
            "best_products": [],
            "reviews_summary": []
        }

        # 1. 네이버 API로 베스트 상품 수집
        best_products = search_naver_shopping(info["search_keyword"], display=10)
        result["best_products"] = best_products

        # 2. 네이버 쇼핑 카탈로그에서 리뷰 수집
        if best_products:
            reviews = get_reviews_for_competitor(name, best_products, headless=self.headless)
            result["reviews_summary"] = reviews

        return result


# ──────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────
if __name__ == "__main__":
    crawler = CompetitorCrawler(headless=False)
    results = crawler.crawl_all()
    print(json.dumps(results, ensure_ascii=False, indent=2))
