"""
ESM플러스 크롤러 - 옥션 + 지마켓 (meditial 스토어)
공개 쇼핑몰 페이지 크롤링 (로그인 불필요)
"""
from datetime import datetime, timedelta
import re
from .base import BaseCrawler


class ESMPlusCrawler(BaseCrawler):
    CHANNEL_NAME = "ESM플러스"
    LOGIN_URL = ""

    AUCTION_URL = "https://stores.auction.co.kr/meditial"
    GMARKET_URL = "https://minishop.gmarket.co.kr/meditial"

    def login(self) -> bool:
        return True

    def collect_cs(self, days_back: int = 7) -> list:
        return []

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        return False

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        return False

    def _normalize_date(self, date_str: str) -> str:
        date_str = date_str.strip()
        m = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', date_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        m2 = re.search(r'(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})', date_str)
        if m2:
            year = int(m2.group(1))
            year = 2000 + year if year < 100 else year
            return f"{year}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
        return datetime.now().strftime("%Y-%m-%d")

    def collect_reviews(self, days_back: int = 7) -> list:
        reviews = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        print(f"[{self.CHANNEL_NAME}] 옥션 리뷰 수집 시작", flush=True)
        auction_reviews = self._collect_auction_reviews(days_back, cutoff_date)
        reviews.extend(auction_reviews)
        print(f"[{self.CHANNEL_NAME}] 옥션 리뷰 {len(auction_reviews)}개 수집", flush=True)

        print(f"[{self.CHANNEL_NAME}] 지마켓 리뷰 수집 시작", flush=True)
        gmarket_reviews = self._collect_gmarket_reviews(days_back, cutoff_date)
        reviews.extend(gmarket_reviews)
        print(f"[{self.CHANNEL_NAME}] 지마켓 리뷰 {len(gmarket_reviews)}개 수집", flush=True)

        print(f"[{self.CHANNEL_NAME}] 총 {len(reviews)}개 리뷰 수집 완료", flush=True)
        return reviews

    # ── 옥션 ────────────────────────────────────────────

    def _collect_auction_reviews(self, days_back: int, cutoff_date: datetime) -> list:
        reviews = []
        product_urls = self._get_auction_product_urls()
        print(f"[{self.CHANNEL_NAME}] 옥션 상품 {len(product_urls)}개 발견", flush=True)

        for product_url in product_urls:
            self._collect_auction_product_reviews(product_url, reviews, cutoff_date)
            self.sleep(1.5, 2.5)

        return reviews

    def _get_auction_product_urls(self) -> list:
        product_urls = []
        page_num = 1

        while True:
            url = f"{self.AUCTION_URL}?page={page_num}"
            print(f"[{self.CHANNEL_NAME}] 옥션 스토어 페이지 {page_num}: {url}", flush=True)

            try:
                self.page.goto(url, wait_until="networkidle", timeout=20000)
                self.sleep(1.0, 2.0)
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 옥션 스토어 로드 실패: {e}", flush=True)
                break

            links = self.page.query_selector_all(
                "a[href*='ItemNo='], a[href*='auction.co.kr/Item']"
            )
            if not links:
                break

            new_urls = []
            for link in links:
                href = link.get_attribute("href") or ""
                if href and href not in product_urls:
                    new_urls.append(href)
                    product_urls.append(href)

            if not new_urls:
                break

            page_num += 1
            self.sleep(1.0, 2.0)

        return product_urls

    def _collect_auction_product_reviews(self, product_url: str, reviews: list, cutoff_date: datetime):
        print(f"[{self.CHANNEL_NAME}] 옥션 상품 리뷰 수집: {product_url}", flush=True)

        try:
            self.page.goto(product_url, wait_until="networkidle", timeout=20000)
            self.sleep(1.5, 2.5)
        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 옥션 상품 로드 실패: {e}", flush=True)
            return

        # 구매후기 탭 클릭
        for tab_sel in ["button:has-text('구매후기')", "a:has-text('구매후기')", "li:has-text('구매후기')"]:
            try:
                tab = self.page.query_selector(tab_sel)
                if tab and tab.is_visible():
                    tab.click()
                    self.sleep(1.5, 2.5)
                    break
            except Exception:
                continue

        page_num = 1
        stop = False

        while not stop:
            items = []
            for item_sel in [
                ".review-list li",
                "#buyerReviewList li",
                "[class*='review'] li",
                ".reviewList li",
            ]:
                items = self.page.query_selector_all(item_sel)
                if items:
                    break

            if not items:
                break

            parsed_count = 0
            for item in items:
                try:
                    review = self._parse_esm_review_item(item, "옥션")
                    if not review:
                        continue

                    review_date_str = review.get("review_date", "")
                    if review_date_str:
                        try:
                            review_date = datetime.strptime(review_date_str, "%Y-%m-%d")
                            if review_date < cutoff_date:
                                stop = True
                                break
                        except Exception:
                            pass

                    reviews.append(review)
                    parsed_count += 1
                except Exception:
                    continue

            print(f"[{self.CHANNEL_NAME}] 옥션 리뷰 페이지 {page_num}: {parsed_count}개", flush=True)

            if stop:
                break

            next_btn = self.page.query_selector(
                ".paging a:has-text('다음'), .pagination a[rel='next'], a.next"
            )
            if not next_btn:
                break

            try:
                next_btn.click()
                self.sleep(1.5, 2.5)
                page_num += 1
            except Exception:
                break

            if page_num > 20:
                break

    # ── 지마켓 ───────────────────────────────────────────

    def _collect_gmarket_reviews(self, days_back: int, cutoff_date: datetime) -> list:
        reviews = []
        product_urls = self._get_gmarket_product_urls()
        print(f"[{self.CHANNEL_NAME}] 지마켓 상품 {len(product_urls)}개 발견", flush=True)

        for product_url in product_urls:
            self._collect_gmarket_product_reviews(product_url, reviews, cutoff_date)
            self.sleep(1.5, 2.5)

        return reviews

    def _get_gmarket_product_urls(self) -> list:
        product_urls = []
        page_num = 1

        while True:
            url = f"{self.GMARKET_URL}?page={page_num}"
            print(f"[{self.CHANNEL_NAME}] 지마켓 스토어 페이지 {page_num}: {url}", flush=True)

            try:
                self.page.goto(url, wait_until="networkidle", timeout=20000)
                self.sleep(1.0, 2.0)
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 지마켓 스토어 로드 실패: {e}", flush=True)
                break

            links = self.page.query_selector_all(
                "a[href*='itemno='], a[href*='gmarket.co.kr/Item']"
            )
            if not links:
                break

            new_urls = []
            for link in links:
                href = link.get_attribute("href") or ""
                if href and href not in product_urls:
                    new_urls.append(href)
                    product_urls.append(href)

            if not new_urls:
                break

            page_num += 1
            self.sleep(1.0, 2.0)

        return product_urls

    def _collect_gmarket_product_reviews(self, product_url: str, reviews: list, cutoff_date: datetime):
        print(f"[{self.CHANNEL_NAME}] 지마켓 상품 리뷰 수집: {product_url}", flush=True)

        try:
            self.page.goto(product_url, wait_until="domcontentloaded", timeout=15000)
            self.sleep(2.0, 3.0)
        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 지마켓 상품 로드 실패: {e}", flush=True)
            return

        # 구매후기 탭 클릭
        for tab_sel in ["button:has-text('후기')", "a:has-text('구매후기')", "li:has-text('후기')"]:
            try:
                tab = self.page.query_selector(tab_sel)
                if tab and tab.is_visible():
                    tab.click()
                    self.sleep(1.5, 2.5)
                    break
            except Exception:
                continue

        page_num = 1
        stop = False

        while not stop:
            items = []
            for item_sel in [
                ".review-list li",
                "#buyerReviewList li",
                "[class*='review'] li",
                ".reviewList li",
            ]:
                items = self.page.query_selector_all(item_sel)
                if items:
                    break

            if not items:
                break

            parsed_count = 0
            for item in items:
                try:
                    review = self._parse_esm_review_item(item, "지마켓")
                    if not review:
                        continue

                    review_date_str = review.get("review_date", "")
                    if review_date_str:
                        try:
                            review_date = datetime.strptime(review_date_str, "%Y-%m-%d")
                            if review_date < cutoff_date:
                                stop = True
                                break
                        except Exception:
                            pass

                    reviews.append(review)
                    parsed_count += 1
                except Exception:
                    continue

            print(f"[{self.CHANNEL_NAME}] 지마켓 리뷰 페이지 {page_num}: {parsed_count}개", flush=True)

            if stop:
                break

            next_btn = self.page.query_selector(
                ".paging a:has-text('다음'), .pagination a[rel='next'], a.next"
            )
            if not next_btn:
                break

            try:
                next_btn.click()
                self.sleep(1.5, 2.5)
                page_num += 1
            except Exception:
                break

            if page_num > 20:
                break

    # ── 공통 파싱 ────────────────────────────────────────

    def _parse_esm_review_item(self, item, platform: str) -> dict:
        try:
            # 별점
            rating = 5
            rating_el = item.query_selector("[class*='star'], [class*='rating'], [class*='score']")
            if rating_el:
                rating_text = rating_el.inner_text().strip()
                m = re.search(r'(\d+)', rating_text)
                if m:
                    rating = min(5, max(1, int(m.group(1))))

            # 내용
            content = ""
            for content_sel in [
                "[class*='review_cont']", "[class*='reviewCont']",
                "[class*='content']", "[class*='text']", "p",
            ]:
                content_el = item.query_selector(content_sel)
                if content_el:
                    content = content_el.inner_text().strip()
                    if content:
                        break
            if not content:
                content = item.inner_text().strip()

            # 날짜
            review_date = datetime.now().strftime("%Y-%m-%d")
            date_el = item.query_selector("[class*='date'], time, .date")
            if date_el:
                date_text = date_el.inner_text().strip()
                if date_text:
                    review_date = self._normalize_date(date_text)

            # 상품명
            product_name = ""
            product_el = item.query_selector("[class*='product'], [class*='goods'], [class*='item']")
            if product_el:
                product_name = product_el.inner_text().strip()

            # 고객 ID
            customer_id = ""
            author_el = item.query_selector("[class*='author'], [class*='user'], [class*='id']")
            if author_el:
                customer_id = author_el.inner_text().strip()

            # 리뷰 ID
            review_id = item.get_attribute("data-review-id") or item.get_attribute("id") or ""

            if not content:
                return None

            return {
                "channel": self.CHANNEL_NAME,
                "product_name": product_name,
                "option_name": "",
                "customer_id": customer_id,
                "order_number": "",
                "rating": rating,
                "content": content,
                "review_date": review_date,
                "review_id_on_channel": review_id,
            }
        except Exception:
            return None
