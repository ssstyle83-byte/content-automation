"""
SSG 크롤러 - 메디셜 브랜드샵
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

        const candidates = Array.from(document.querySelectorAll(
            'ul > li, ol > li, ' +
            '[class*="review_list"] > *, [class*="reviewList"] > *, ' +
            '[class*="review-list"] > *, ' +
            '[class*="cmt_list"] > *, ' +
            '[class*="review"] li, [id*="review"] li, ' +
            '[class*="review"] > div, [id*="review"] > div, ' +
            '[class*="Review"] li, [class*="Review"] > div, ' +
            '.review_list li, .ssg_review li'
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
            const ratingEl = el.querySelector('[class*="rating"], [class*="star"], [class*="score"], [aria-label*="점"]');
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

            const prdEl = el.querySelector('[class*="product"], [class*="goods_name"]');
            const productName = prdEl ? (prdEl.innerText || '').trim().substring(0, 100) : '';
            const optEl = el.querySelector('[class*="option"], [class*="opt"]');
            const optionName = optEl ? (optEl.innerText || '').trim() : '';
            const authorEl = el.querySelector('[class*="author"], [class*="user"], [class*="nick"]');
            const customerId = authorEl ? (authorEl.innerText || '').trim() : '';
            const reviewId = el.getAttribute('data-review-id') || el.id || '';

            results.push({ content, dateStr, rating, productName, optionName, customerId, reviewId });
        }
        return results;
    }
"""


class SSGCrawler(BaseCrawler):
    CHANNEL_NAME = "SSG"
    LOGIN_URL = ""

    BRAND_SHOP_URL = (
        "https://www.ssg.com/disp/brandShop.ssg"
        "?brandId=3000077368&ctgId=6000092907"
    )

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

        print(f"[{self.CHANNEL_NAME}] 브랜드샵 상품 목록 수집 시작", flush=True)
        item_ids = self._get_item_ids()
        print(f"[{self.CHANNEL_NAME}] 상품 {len(item_ids)}개 발견", flush=True)

        for item_id in item_ids:
            self._collect_item_reviews(item_id, reviews, days_back, cutoff_date)
            self.sleep(1.5, 2.5)

        print(f"[{self.CHANNEL_NAME}] 총 {len(reviews)}개 리뷰 수집 완료", flush=True)
        return reviews

    def _get_item_ids(self) -> list:
        seen = set()
        item_ids = []
        page_num = 1

        while True:
            url = f"{self.BRAND_SHOP_URL}&page={page_num}"
            print(f"[{self.CHANNEL_NAME}] 브랜드샵 페이지 {page_num}: {url}", flush=True)

            try:
                self.page.goto(url, wait_until="networkidle", timeout=20000)
                self.sleep(1.5, 2.5)
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 브랜드샵 페이지 로드 실패: {e}", flush=True)
                break

            print(f"[{self.CHANNEL_NAME}] 페이지 타이틀: {self.page.title()}", flush=True)

            ids = self.page.evaluate("""
                () => {
                    const ids = [];
                    const seen = new Set();
                    Array.from(document.querySelectorAll('a')).forEach(a => {
                        const href = a.href || '';
                        const m = href.match(/itemId=(\\d+)/);
                        if (m && !seen.has(m[1])) {
                            seen.add(m[1]);
                            ids.push(m[1]);
                        }
                    });
                    return ids;
                }
            """)
            print(f"[{self.CHANNEL_NAME}] 페이지 {page_num} 상품 {len(ids)}개 발견", flush=True)

            if not ids:
                break

            new_found = False
            for iid in ids:
                if iid not in seen:
                    seen.add(iid)
                    item_ids.append(iid)
                    new_found = True

            if not new_found:
                break

            page_num += 1
            self.sleep(1.0, 2.0)

        return item_ids

    def _collect_item_reviews(self, item_id: str, reviews: list, days_back: int, cutoff_date: datetime):
        url = f"https://www.ssg.com/item/itm_detail.ssg?itemId={item_id}"
        print(f"[{self.CHANNEL_NAME}] 상품 {item_id} 리뷰 수집: {url}", flush=True)

        try:
            self.page.goto(url, wait_until="networkidle", timeout=20000)
            self.sleep(1.5, 2.5)
        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 상품 {item_id} 로드 실패: {e}", flush=True)
            return

        # 구매후기 탭 클릭 - Playwright 셀렉터
        tab_clicked = False
        for tab_sel in [
            "a:has-text('구매후기')",
            "button:has-text('구매후기')",
            "a:has-text('리뷰')",
            "li:has-text('구매후기') > a",
            "[data-tab='review']",
            "#reviewTab",
            "[href*='review']",
        ]:
            try:
                tab = self.page.query_selector(tab_sel)
                if tab and tab.is_visible():
                    tab.click()
                    self.sleep(2.0, 3.0)
                    tab_clicked = True
                    print(f"[{self.CHANNEL_NAME}] 구매후기 탭 클릭 성공: {tab_sel}", flush=True)
                    break
            except Exception:
                continue

        if not tab_clicked:
            # JS로 탭 클릭 시도 (텍스트 기반)
            js_clicked = self.page.evaluate("""
                () => {
                    const els = Array.from(document.querySelectorAll('a, button, li'));
                    const el = els.find(e => {
                        const t = (e.innerText || '').trim();
                        return t.includes('구매후기') || t.includes('리뷰');
                    });
                    if (el) {
                        el.click();
                        return el.innerText.trim();
                    }
                    return null;
                }
            """)
            if js_clicked:
                print(f"[{self.CHANNEL_NAME}] JS 탭 클릭 성공: '{js_clicked}'", flush=True)
                self.sleep(2.0, 3.0)
                tab_clicked = True
            else:
                print(f"[{self.CHANNEL_NAME}] 상품 {item_id}: 구매후기 탭 찾기 실패", flush=True)
                # 탭 없어도 스크롤해서 리뷰 섹션 찾기 시도
                self.page.evaluate("""
                    () => {
                        const el = document.querySelector('.review_list, [id*="review"], [class*="review"]');
                        if (el) el.scrollIntoView();
                    }
                """)
                self.sleep(1.0, 2.0)

        page_num = 1
        stop = False

        while not stop:
            items = self.page.evaluate(_REVIEW_EXTRACT_JS)

            if not items:
                print(f"[{self.CHANNEL_NAME}] 상품 {item_id} 페이지 {page_num}: 리뷰 없음", flush=True)
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
                        "product_name": (item.get("productName") or "").strip() or f"상품#{item_id}",
                        "option_name": (item.get("optionName") or "").strip(),
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

            print(f"[{self.CHANNEL_NAME}] 상품 {item_id} 리뷰 페이지 {page_num}: {parsed_count}개 (후보 {len(items)}개)", flush=True)

            if stop:
                break

            # 다음 페이지 버튼 (JS)
            has_next = self.page.evaluate("""
                () => {
                    const els = Array.from(document.querySelectorAll('.pagination a, .paging a, a, button'));
                    return els.some(el => {
                        const t = (el.innerText || '').trim();
                        const cls = el.className || '';
                        return t === '다음' || (cls.includes('next') && !cls.includes('disabled'));
                    });
                }
            """)
            if not has_next:
                break

            try:
                clicked = self.page.evaluate("""
                    () => {
                        const els = Array.from(document.querySelectorAll('.pagination a, .paging a, a, button'));
                        const el = els.find(e => (e.innerText || '').trim() === '다음');
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
