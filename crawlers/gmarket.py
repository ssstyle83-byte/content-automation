"""
지마켓 크롤러 - meditial 스토어
공개 쇼핑몰 페이지 크롤링 (로그인 불필요)
"""
from datetime import datetime, timedelta
import re
from .base import BaseCrawler


class GmarketCrawler(BaseCrawler):
    CHANNEL_NAME = "지마켓"
    LOGIN_URL = ""

    STORE_URL = "https://minishop.gmarket.co.kr/meditial"

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
        product_urls = self._get_product_urls()
        print(f"[{self.CHANNEL_NAME}] 상품 {len(product_urls)}개 발견", flush=True)

        for product_url in product_urls:
            self._collect_product_reviews(product_url, reviews, cutoff_date)
            self.sleep(1.5, 2.5)

        print(f"[{self.CHANNEL_NAME}] 총 {len(reviews)}개 리뷰 수집 완료", flush=True)
        return reviews

    def _get_product_urls(self) -> list:
        seen = set()
        product_urls = []
        page_num = 1

        while True:
            url = f"{self.STORE_URL}?page={page_num}"
            print(f"[{self.CHANNEL_NAME}] 스토어 페이지 {page_num}: {url}", flush=True)

            try:
                self.page.goto(url, wait_until="networkidle", timeout=20000)
                self.sleep(1.5, 2.5)
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 스토어 로드 실패: {e}", flush=True)
                break

            print(f"[{self.CHANNEL_NAME}] 페이지 타이틀: {self.page.title()}", flush=True)

            # JS a.href property 기반 추출 (지마켓 상품 URL 패턴)
            urls = self.page.evaluate("""
                () => {
                    const urls = [];
                    const seen = new Set();
                    Array.from(document.querySelectorAll('a')).forEach(a => {
                        const href = a.href || '';
                        // 지마켓 상품 URL: itemno= 또는 gmarket.co.kr/Item 또는 goodsCode=
                        if ((href.includes('itemno=') || href.includes('gmarket.co.kr/Item') ||
                             href.includes('goodsCode=')) && !seen.has(href)) {
                            seen.add(href);
                            urls.push(href);
                        }
                    });
                    return urls;
                }
            """)
            print(f"[{self.CHANNEL_NAME}] 페이지 {page_num} 상품 {len(urls)}개 발견", flush=True)

            if not urls:
                break

            new_found = False
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    product_urls.append(u)
                    new_found = True

            if not new_found:
                break

            page_num += 1
            self.sleep(1.0, 2.0)

        return product_urls

    def _collect_product_reviews(self, product_url: str, reviews: list, cutoff_date: datetime):
        print(f"[{self.CHANNEL_NAME}] 상품 리뷰 수집: {product_url}", flush=True)

        try:
            self.page.goto(product_url, wait_until="domcontentloaded", timeout=20000)
            self.sleep(2.0, 3.0)
        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 상품 로드 실패: {e}", flush=True)
            return

        # 구매후기 탭 클릭
        for tab_sel in ["button:has-text('후기')", "a:has-text('구매후기')", "li:has-text('후기')"]:
            try:
                tab = self.page.query_selector(tab_sel)
                if tab and tab.is_visible():
                    tab.click()
                    self.sleep(1.5, 2.5)
                    print(f"[{self.CHANNEL_NAME}] 구매후기 탭 클릭 성공", flush=True)
                    break
            except Exception:
                continue

        page_num = 1
        stop = False

        while not stop:
            items = self.page.evaluate("""
                () => {
                    const DATE_RE = /\\d{4}[.\\-\\/]\\d{1,2}[.\\-\\/]\\d{1,2}/;
                    const results = [];
                    const containers = Array.from(document.querySelectorAll(
                        '.review-list li, #buyerReviewList li, [class*="review"] li, .reviewList li, ul > li, ol > li'
                    ));

                    for (const li of containers) {
                        const fullText = (li.innerText || '').trim();
                        if (fullText.length < 15) continue;
                        if (!DATE_RE.test(fullText)) continue;

                        const dateMatch = fullText.match(/(\\d{4})[.\\-\\/](\\d{1,2})[.\\-\\/](\\d{1,2})/);
                        const dateStr = dateMatch ? dateMatch[1] + '.' + dateMatch[2] + '.' + dateMatch[3] : '';

                        let rating = 5;
                        const ratingEl = li.querySelector('[class*="star"], [class*="rating"], [class*="score"], [aria-label*="점"]');
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
                            if (/^[\\d,]+$/.test(line)) continue;
                            if (line.length > content.length) content = line;
                        }
                        if (!content) content = fullText.substring(0, 500);
                        if (content.length < 10) continue;

                        const prdEl = li.querySelector('[class*="product"], [class*="goods"], [class*="item"]');
                        const productName = prdEl ? (prdEl.innerText || '').trim().substring(0, 100) : '';
                        const authorEl = li.querySelector('[class*="author"], [class*="user"], [class*="id"]');
                        const customerId = authorEl ? (authorEl.innerText || '').trim() : '';
                        const reviewId = li.getAttribute('data-review-id') || li.id || '';

                        results.push({ content, dateStr, rating, productName, customerId, reviewId });
                    }
                    return results;
                }
            """)

            if not items:
                print(f"[{self.CHANNEL_NAME}] 리뷰 페이지 {page_num}: 리뷰 없음", flush=True)
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
                        "product_name": (item.get("productName") or "").strip(),
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

            print(f"[{self.CHANNEL_NAME}] 리뷰 페이지 {page_num}: {parsed_count}개 (후보 {len(items)}개)", flush=True)

            if stop:
                break

            has_next = self.page.evaluate("""
                () => {
                    const els = Array.from(document.querySelectorAll('.paging a, .pagination a, a'));
                    return els.some(el => {
                        const t = (el.innerText || '').trim();
                        const rel = el.getAttribute('rel') || '';
                        return t === '다음' || rel === 'next';
                    });
                }
            """)
            if not has_next:
                break

            try:
                clicked = self.page.evaluate("""
                    () => {
                        const els = Array.from(document.querySelectorAll('.paging a, .pagination a, a'));
                        const el = els.find(e => {
                            const t = (e.innerText || '').trim();
                            const rel = e.getAttribute('rel') || '';
                            return t === '다음' || rel === 'next';
                        });
                        if (el) { el.click(); return true; }
                        return false;
                    }
                """)
                if not clicked:
                    break
                self.sleep(1.5, 2.5)
                page_num += 1
            except Exception:
                break

            if page_num > 20:
                break
