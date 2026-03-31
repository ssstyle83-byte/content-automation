"""
11번가 크롤러 - shop.11st.co.kr/stores/652740
공개 쇼핑몰 페이지 크롤링 (로그인 불필요)
"""
from datetime import datetime, timedelta
import re
from .base import BaseCrawler

# 리뷰 추출 공통 JS (ul/ol li + div 구조 모두 탐색)
_REVIEW_EXTRACT_JS = """
    () => {
        const DATE_RE = /\\d{4}[.\\-\\/]\\d{1,2}[.\\-\\/]\\d{1,2}/;
        const results = [];

        // li + div 모두 후보로
        const candidates = Array.from(document.querySelectorAll(
            'ul > li, ol > li, ' +
            '[class*="review"] li, [class*="Review"] li, ' +
            '[class*="review_list"] > *, [class*="reviewList"] > *, ' +
            '[class*="review-list"] > *, ' +
            '[class*="Review_item"], [class*="review_item"], ' +
            '[class*="ReviewItem"], [class*="reviewItem"], ' +
            '[id*="review"] li, [id*="Review"] li, ' +
            '[class*="review"] > div, [class*="Review"] > div'
        ));

        const seen = new Set();
        for (const el of candidates) {
            const fullText = (el.innerText || '').trim();
            if (fullText.length < 15) continue;
            if (!DATE_RE.test(fullText)) continue;
            if (seen.has(fullText)) continue;
            seen.add(fullText);

            const dateMatch = fullText.match(/(\\d{4})[.\\-\\/](\\d{1,2})[.\\-\\/](\\d{1,2})/);
            const dateStr = dateMatch ? dateMatch[1] + '.' + dateMatch[2] + '.' + dateMatch[3] : '';

            let rating = 5;
            const ratingEl = el.querySelector('[class*="star"], [class*="rating"], [class*="score"], [aria-label*="점"]');
            if (ratingEl) {
                const rl = ratingEl.getAttribute('aria-label') || ratingEl.getAttribute('title') || ratingEl.innerText || '';
                const rm = rl.match(/(\\d+)/);
                if (rm) rating = Math.min(5, Math.max(1, parseInt(rm[1])));
                const style = ratingEl.getAttribute('style') || '';
                const wm = style.match(/width:\\s*(\\d+(\\.\\d+)?)%/);
                if (wm) rating = Math.round(parseFloat(wm[1]) / 20);
            }

            const lines = fullText.split('\\n').map(t => t.trim()).filter(t => t.length > 0);
            let content = '';
            for (const line of lines) {
                if (DATE_RE.test(line)) continue;
                if (/^[\\d,\\s]+$/.test(line)) continue;
                if (line.length > content.length) content = line;
            }
            if (!content) content = fullText.substring(0, 500);
            if (content.length < 10) continue;

            const prdEl = el.querySelector('[class*="product"], [class*="prd_name"], [class*="goods"]');
            const productName = prdEl ? (prdEl.innerText || '').trim().substring(0, 100) : '';
            const authorEl = el.querySelector('[class*="author"], [class*="user_id"], [class*="buyer"], [class*="nick"]');
            const customerId = authorEl ? (authorEl.innerText || '').trim() : '';
            const reviewId = el.getAttribute('data-review-id') || el.id || '';

            results.push({ content, dateStr, rating, productName, customerId, reviewId });
        }
        return results;
    }
"""


class ElevenCrawler(BaseCrawler):
    CHANNEL_NAME = "11번가"
    LOGIN_URL = ""

    STORE_URL = "https://shop.11st.co.kr/stores/652740"

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

        print(f"[{self.CHANNEL_NAME}] 스토어 상품 목록 수집 시작", flush=True)
        product_nos = self._get_product_nos()
        print(f"[{self.CHANNEL_NAME}] 상품 {len(product_nos)}개 발견", flush=True)

        for product_no in product_nos:
            self._collect_product_reviews(product_no, reviews, days_back, cutoff_date)
            self.sleep(1.5, 2.5)

        print(f"[{self.CHANNEL_NAME}] 총 {len(reviews)}개 리뷰 수집 완료", flush=True)
        return reviews

    def _get_product_nos(self) -> list:
        seen = set()
        product_nos = []
        page_num = 1

        while True:
            url = f"{self.STORE_URL}?page={page_num}"
            print(f"[{self.CHANNEL_NAME}] 스토어 페이지 {page_num}: {url}", flush=True)

            try:
                self.page.goto(url, wait_until="networkidle", timeout=20000)
                self.sleep(1.5, 2.5)
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 스토어 페이지 로드 실패: {e}", flush=True)
                break

            print(f"[{self.CHANNEL_NAME}] 페이지 타이틀: {self.page.title()}", flush=True)

            nos = self.page.evaluate("""
                () => {
                    const nos = [];
                    const seen = new Set();
                    Array.from(document.querySelectorAll('a')).forEach(a => {
                        const href = a.href || '';
                        let m = href.match(/\\/products?\\/(\\d+)/);
                        if (!m) m = href.match(/product_no=(\\d+)/);
                        if (m && !seen.has(m[1])) {
                            seen.add(m[1]);
                            nos.push(m[1]);
                        }
                    });
                    return nos;
                }
            """)
            print(f"[{self.CHANNEL_NAME}] 페이지 {page_num} 상품 {len(nos)}개 발견", flush=True)

            if not nos:
                break

            new_found = False
            for pno in nos:
                if pno not in seen:
                    seen.add(pno)
                    product_nos.append(pno)
                    new_found = True

            if not new_found:
                break

            page_num += 1
            self.sleep(1.0, 2.0)

        return product_nos

    def _collect_product_reviews(self, product_no: str, reviews: list, days_back: int, cutoff_date: datetime):
        print(f"[{self.CHANNEL_NAME}] 상품 {product_no} 리뷰 수집", flush=True)

        # 전략 1: 상품 페이지 → 리뷰 탭 클릭
        product_url = f"https://www.11st.co.kr/products/{product_no}"
        try:
            self.page.goto(product_url, wait_until="networkidle", timeout=20000)
            self.sleep(1.5, 2.5)

            # 리뷰/구매후기 탭 클릭
            tab_clicked = False
            for tab_sel in [
                "a:has-text('구매후기')",
                "button:has-text('구매후기')",
                "a:has-text('리뷰')",
                "li:has-text('구매후기') a",
                "#reviewTab",
                "[href*='review']",
            ]:
                try:
                    tab = self.page.query_selector(tab_sel)
                    if tab and tab.is_visible():
                        tab.click()
                        self.sleep(2.0, 3.0)
                        tab_clicked = True
                        print(f"[{self.CHANNEL_NAME}] 상품 {product_no}: 리뷰 탭 클릭 성공 ({tab_sel})", flush=True)
                        break
                except Exception:
                    continue

            if not tab_clicked:
                print(f"[{self.CHANNEL_NAME}] 상품 {product_no}: 탭 클릭 실패, JS로 스크롤 시도", flush=True)
                # JS로 리뷰 섹션 anchor 이동
                self.page.evaluate("""
                    () => {
                        const el = document.querySelector('#sec_review, #reviewArea, [id*="review"]');
                        if (el) el.scrollIntoView();
                    }
                """)
                self.sleep(1.5, 2.5)

        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 상품 {product_no} 페이지 로드 실패: {e}", flush=True)
            return

        page_num = 1
        stop = False

        while not stop:
            items = self.page.evaluate(_REVIEW_EXTRACT_JS)

            if not items:
                # 전략 2: /reviews URL 직접 접근
                if page_num == 1:
                    try:
                        review_url = f"https://www.11st.co.kr/products/{product_no}/reviews?page=1"
                        self.page.goto(review_url, wait_until="networkidle", timeout=20000)
                        self.sleep(1.5, 2.5)
                        items = self.page.evaluate(_REVIEW_EXTRACT_JS)
                    except Exception:
                        pass

                if not items:
                    print(f"[{self.CHANNEL_NAME}] 상품 {product_no} 페이지 {page_num}: 리뷰 없음", flush=True)
                    break

            parsed_count = 0
            for item in items:
                try:
                    content = (item.get("content") or "").strip()
                    if not content or len(content) < 10:
                        continue

                    date_str = item.get("dateStr") or ""
                    review_date = self._normalize_date(date_str) if date_str else datetime.now().strftime("%Y-%m-%d")

                    try:
                        rd = datetime.strptime(review_date, "%Y-%m-%d")
                        if rd < cutoff_date:
                            stop = True
                            break
                    except Exception:
                        pass

                    reviews.append({
                        "channel": self.CHANNEL_NAME,
                        "product_name": (item.get("productName") or "").strip() or f"상품#{product_no}",
                        "option_name": "",
                        "customer_id": (item.get("customerId") or "").strip(),
                        "order_number": "",
                        "rating": item.get("rating") or 5,
                        "content": content,
                        "review_date": review_date,
                        "review_id_on_channel": (item.get("reviewId") or "").strip(),
                    })
                    parsed_count += 1
                except Exception:
                    continue

            print(f"[{self.CHANNEL_NAME}] 상품 {product_no} 리뷰 페이지 {page_num}: {parsed_count}개 (후보 {len(items)}개)", flush=True)

            if stop:
                break

            # 다음 페이지: URL 파라미터 방식
            page_num += 1
            if page_num > 20:
                break

            try:
                next_url = f"https://www.11st.co.kr/products/{product_no}/reviews?page={page_num}"
                self.page.goto(next_url, wait_until="networkidle", timeout=20000)
                self.sleep(1.5, 2.5)
            except Exception:
                break
