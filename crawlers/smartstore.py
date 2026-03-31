"""
네이버 스마트스토어 크롤러 - brand.naver.com/meditial
공개 쇼핑몰 페이지 크롤링 (로그인 불필요)
"""
from datetime import datetime, timedelta
import re
from .base import BaseCrawler


class SmartStoreCrawler(BaseCrawler):
    CHANNEL_NAME = "스마트스토어"
    LOGIN_URL = ""

    BRAND_URL = "https://brand.naver.com/meditial"

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

        print(f"[{self.CHANNEL_NAME}] 브랜드 스토어 상품 목록 수집 시작", flush=True)
        product_ids = self._get_product_ids()
        print(f"[{self.CHANNEL_NAME}] 상품 {len(product_ids)}개 발견", flush=True)

        for product_id in product_ids:
            self._collect_product_reviews(product_id, reviews, days_back, cutoff_date)
            self.sleep(1.5, 2.5)

        print(f"[{self.CHANNEL_NAME}] 총 {len(reviews)}개 리뷰 수집 완료", flush=True)
        return reviews

    def _get_product_ids(self) -> list:
        seen = set()
        product_ids = []

        urls_to_try = [
            self.BRAND_URL,
            f"{self.BRAND_URL}/category/ALL",
        ]

        for url in urls_to_try:
            print(f"[{self.CHANNEL_NAME}] 상품 목록: {url}", flush=True)
            try:
                self.page.goto(url, wait_until="networkidle", timeout=25000)
                self.sleep(3.0, 4.0)
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 상품 목록 로드 실패: {e}", flush=True)
                continue

            print(f"[{self.CHANNEL_NAME}] 페이지 타이틀: {self.page.title()}", flush=True)

            # a.href property 기반 JS 추출 (React SPA resolved URL)
            ids = self.page.evaluate("""
                () => {
                    const ids = [];
                    const seen = new Set();
                    Array.from(document.querySelectorAll('a')).forEach(a => {
                        const href = a.href || '';
                        const m = href.match(/\\/meditial\\/products\\/(\\d+)/);
                        if (m && !seen.has(m[1])) {
                            seen.add(m[1]);
                            ids.push(m[1]);
                        }
                    });
                    console.log('[SmartStore] found product ids:', ids.length);
                    return ids;
                }
            """)
            print(f"[{self.CHANNEL_NAME}] 이 페이지 상품 {len(ids)}개 발견", flush=True)
            for pid in ids:
                if pid not in seen:
                    seen.add(pid)
                    product_ids.append(pid)

        return product_ids

    def _extract_reviews_from_frame(self, frame):
        """프레임에서 리뷰 JS 추출 - 전체 DOM 스캔 (obfuscated class 대응)."""
        return frame.evaluate("""
            () => {
                const DATE_RE = /\\d{4}[.\\-\\/]\\d{1,2}[.\\-\\/]\\d{1,2}/;
                const results = [];
                const seen = new Set();

                // 전체 DOM 스캔: 날짜를 포함하되 자식 중 날짜 포함 자식이 없는 leaf 요소 탐색
                const allEls = Array.from(document.querySelectorAll(
                    'li, article, [data-review-id], [data-id]'
                ));

                // fallback: 모든 요소 스캔
                const candidates = allEls.length > 0 ? allEls :
                    Array.from(document.querySelectorAll('*'));

                for (const el of candidates) {
                    const fullText = (el.innerText || '').trim();
                    if (fullText.length < 30 || fullText.length > 3000) continue;
                    if (!DATE_RE.test(fullText)) continue;
                    if (seen.has(fullText)) continue;

                    // 자식 중 날짜 포함한 자식이 있으면 부모 컨테이너이므로 스킵
                    // (리뷰 목록 전체 컨테이너가 아닌 개별 리뷰 항목을 찾기 위해)
                    let childHasDate = false;
                    for (const child of el.children) {
                        const ct = (child.innerText || '').trim();
                        if (ct.length > 20 && DATE_RE.test(ct)) {
                            childHasDate = true;
                            break;
                        }
                    }
                    if (childHasDate) continue;

                    seen.add(fullText);

                    const dateMatch = fullText.match(/(\\d{4})[.\\-\\/](\\d{1,2})[.\\-\\/](\\d{1,2})/);
                    const dateStr = dateMatch
                        ? dateMatch[1] + '.' + dateMatch[2] + '.' + dateMatch[3]
                        : '';

                    let rating = 5;
                    const ratingEl = el.querySelector('[aria-label*="점"], [title*="점"]');
                    if (ratingEl) {
                        const rl = ratingEl.getAttribute('aria-label') || ratingEl.getAttribute('title') || '';
                        const rm = rl.match(/(\\d+)/);
                        if (rm) rating = Math.min(5, Math.max(1, parseInt(rm[1])));
                    }
                    // style width% 기반 별점
                    el.querySelectorAll('[style*="width"]').forEach(se => {
                        const wm = (se.getAttribute('style') || '').match(/width:\\s*(\\d+(\\.\\d+)?)%/);
                        if (wm) {
                            const r = Math.round(parseFloat(wm[1]) / 20);
                            if (r >= 1 && r <= 5) rating = r;
                        }
                    });

                    const lines = fullText.split('\\n').map(t => t.trim()).filter(t => t.length > 0);
                    let content = '';
                    for (const line of lines) {
                        if (DATE_RE.test(line)) continue;
                        if (/^[\\d,\\s점★☆]+$/.test(line)) continue;
                        if (line.length > content.length) content = line;
                    }
                    if (!content) content = fullText.substring(0, 500);
                    if (content.length < 10) continue;

                    const reviewId = el.getAttribute('data-review-id') || el.getAttribute('data-id') || el.id || '';

                    results.push({ content, dateStr, rating, productName: '', reviewId });
                }
                return results;
            }
        """)

    def _click_review_tab_in_frame(self, frame) -> bool:
        """프레임 안에서 리뷰 탭 클릭 시도."""
        for tab_sel in [
            "a:has-text('리뷰')",
            "button:has-text('리뷰')",
            "[role='tab']:has-text('리뷰')",
            "li:has-text('리뷰') a",
            "li:has-text('리뷰') button",
        ]:
            try:
                tab = frame.query_selector(tab_sel)
                if tab and tab.is_visible():
                    tab.click()
                    self.sleep(2.0, 3.0)
                    print(f"[{self.CHANNEL_NAME}] 프레임 리뷰 탭 클릭 성공: {tab_sel}", flush=True)
                    return True
            except Exception:
                continue
        return False

    def _collect_product_reviews(self, product_id: str, reviews: list, days_back: int, cutoff_date: datetime):
        # #REVIEW 앵커로 직접 리뷰 섹션 이동
        url = f"https://brand.naver.com/meditial/products/{product_id}#REVIEW"
        print(f"[{self.CHANNEL_NAME}] 상품 {product_id} 리뷰 수집: {url}", flush=True)

        try:
            self.page.goto(url, wait_until="networkidle", timeout=30000)
            self.sleep(3.0, 4.0)
        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 상품 {product_id} 페이지 로드 실패: {e}", flush=True)
            return

        # 모든 프레임 목록 로그
        all_frames = self.page.frames
        print(f"[{self.CHANNEL_NAME}] 상품 {product_id} 프레임 수: {len(all_frames)}", flush=True)
        for i, fr in enumerate(all_frames):
            print(f"[{self.CHANNEL_NAME}]   프레임[{i}]: {fr.url}", flush=True)

        # 리뷰 탭 클릭 — #REVIEW 앵커로 이미 이동했지만 탭도 클릭 시도
        for tab_sel in [
            "[role='tab']:has-text('리뷰')",
            "a:has-text('리뷰')",
            "button:has-text('리뷰')",
        ]:
            try:
                tab = self.page.query_selector(tab_sel)
                if tab and tab.is_visible():
                    tab.click()
                    self.sleep(2.0, 3.0)
                    print(f"[{self.CHANNEL_NAME}] 리뷰 탭 클릭: {tab_sel}", flush=True)
                    break
            except Exception:
                continue

        # 각 프레임에서도 탭 클릭 시도
        for i, fr in enumerate(self.page.frames):
            if "naver.com" in fr.url and fr.url != self.page.url:
                self._click_review_tab_in_frame(fr)

        # 리뷰 섹션 스크롤 → lazy loading 트리거
        self.page.evaluate("""
            () => {
                const el = document.querySelector(
                    '[class*="review"], [id*="review"], [id="REVIEW"]'
                );
                if (el) el.scrollIntoView({ behavior: 'smooth' });
                else window.scrollBy(0, window.innerHeight * 2);
            }
        """)
        self.sleep(2.0, 3.0)

        # 리뷰 요소 로딩 대기 (메인 페이지 또는 프레임)
        for fr in [self.page] + list(self.page.frames):
            try:
                fr.wait_for_selector(
                    "ul > li, [class*='review'] li, [class*='Review'] li",
                    state="attached", timeout=5000
                )
                break
            except Exception:
                continue

        page_num = 1
        stop = False

        while not stop:
            # 메인 페이지 + 모든 프레임에서 리뷰 추출 시도
            items = []

            # 메인 페이지
            try:
                main_items = self._extract_reviews_from_frame(self.page)
                if main_items:
                    items = main_items
                    print(f"[{self.CHANNEL_NAME}] 메인 페이지에서 {len(items)}개 후보", flush=True)
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 메인 페이지 추출 오류: {e}", flush=True)

            # 프레임들 (메인에서 못 찾은 경우)
            if not items:
                for i, fr in enumerate(self.page.frames):
                    try:
                        frame_items = self._extract_reviews_from_frame(fr)
                        if frame_items:
                            items = frame_items
                            print(f"[{self.CHANNEL_NAME}] 프레임[{i}] ({fr.url[:60]})에서 {len(items)}개 후보", flush=True)
                            break
                    except Exception as e:
                        print(f"[{self.CHANNEL_NAME}] 프레임[{i}] 추출 오류: {e}", flush=True)
                        continue

            if not items:
                print(f"[{self.CHANNEL_NAME}] 상품 {product_id} 페이지 {page_num}: 리뷰 없음", flush=True)
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
                        "product_name": (item.get("productName") or "").strip() or f"상품#{product_id}",
                        "option_name": "",
                        "customer_id": "",
                        "order_number": "",
                        "rating": item.get("rating") or 5,
                        "content": content,
                        "review_date": review_date,
                        "review_id_on_channel": (item.get("reviewId") or "").strip(),
                    })
                    parsed_count += 1
                except Exception:
                    continue

            print(f"[{self.CHANNEL_NAME}] 상품 {product_id} 리뷰 페이지 {page_num}: {parsed_count}개 (후보 {len(items)}개)", flush=True)

            if stop:
                break

            has_next = self.page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('button, a'));
                    return btns.some(el => {
                        const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
                        return t === '다음' || t === '다음 페이지';
                    });
                }
            """)
            if not has_next:
                break

            try:
                clicked = self.page.evaluate("""
                    () => {
                        const btns = Array.from(document.querySelectorAll('button, a'));
                        const btn = btns.find(el => {
                            const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
                            return t === '다음' || t === '다음 페이지';
                        });
                        if (btn) { btn.click(); return true; }
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
