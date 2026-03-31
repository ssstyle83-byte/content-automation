"""
카페24 크롤러 - meditial.co.kr
구매후기 게시판에서 전체 수집
"""
from datetime import datetime, timedelta
import re
from .base import BaseCrawler


class Cafe24Crawler(BaseCrawler):
    CHANNEL_NAME = "카페24"
    LOGIN_URL = ""

    STORE_URL = "https://meditial.co.kr"
    REVIEW_BOARD_URL = "https://meditial.co.kr/board/review/list_photo.html?board_no=4"

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
        return ""

    def _parse_date(self, date_text: str) -> str:
        if date_text:
            result = self._normalize_date(date_text)
            if result:
                return result
            m = re.search(r'(\d+)일 전', date_text)
            if m:
                return (datetime.now() - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
            if '어제' in date_text:
                return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            if '오늘' in date_text or '방금' in date_text:
                return datetime.now().strftime("%Y-%m-%d")
        return datetime.now().strftime("%Y-%m-%d")

    def collect_reviews(self, days_back: int = 7) -> list:
        reviews = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        print(f"[{self.CHANNEL_NAME}] 구매후기 게시판 수집 시작", flush=True)
        self._collect_from_board(reviews, cutoff_date)

        print(f"[{self.CHANNEL_NAME}] 총 {len(reviews)}개 리뷰 수집 완료", flush=True)
        return reviews

    def _collect_from_board(self, reviews: list, cutoff_date: datetime):
        page_num = 1

        while True:
            url = f"{self.REVIEW_BOARD_URL}&page={page_num}"
            print(f"[{self.CHANNEL_NAME}] 게시판 페이지 {page_num}", flush=True)

            try:
                self.page.goto(url, wait_until="networkidle", timeout=20000)
                self.sleep(1.5, 2.0)
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 페이지 로드 실패: {e}", flush=True)
                break

            # 리뷰 요소 로딩 대기 (실패해도 계속)
            try:
                self.page.wait_for_selector(
                    "li[class*='review']",
                    state="attached", timeout=10000
                )
            except Exception:
                # 로딩 실패 시 페이지 내용 직접 확인
                pass

            items = self.page.evaluate("""
                () => {
                    const els = Array.from(document.querySelectorAll('li[class*="review"]'));
                    if (els.length === 0) return [];
                    return els
                        .filter(el => el instanceof HTMLElement)
                        .map(el => {
                            // 내용: 가장 긴 텍스트 블록
                            let content = '';
                            const candidates = el.querySelectorAll(
                                'p, [class*="cont"], [class*="text"], [class*="desc"], [class*="review_cont"], span'
                            );
                            for (const c of candidates) {
                                const t = (c.innerText || '').trim();
                                if (t.length > content.length) content = t;
                            }
                            if (!content) content = (el.innerText || '').trim().substring(0, 1000);

                            // 날짜
                            let dateText = '';
                            for (const de of el.querySelectorAll('*')) {
                                const cls = (de.className || '').toString();
                                if (cls.includes('date') || de.tagName === 'TIME') {
                                    const t = (de.innerText || de.getAttribute('datetime') || '').trim();
                                    if (t) { dateText = t; break; }
                                }
                            }

                            // 별점
                            const starEl = el.querySelector(
                                '[class*="star"] em, [class*="rating"] em, [class*="score"] em, [class*="star"]'
                            );
                            const starText = starEl
                                ? (starEl.innerText || starEl.getAttribute('style') || '').trim()
                                : '';

                            // 상품명
                            const prdEl = el.querySelector(
                                'a[href*="product_no"], [class*="prd_name"], [class*="product_name"]'
                            );
                            const productName = prdEl ? (prdEl.innerText || '').trim().substring(0, 150) : '';

                            // 리뷰 ID
                            const linkEl = el.querySelector('a[href*="board_no"], a[href*="no="]');
                            const href = linkEl ? (linkEl.getAttribute('href') || '') : '';
                            const idMatch = href.match(/no=(\\d+)/);
                            const reviewId = idMatch ? idMatch[1] : (el.id || '');

                            // 작성자
                            const authorEl = el.querySelector(
                                '[class*="writer"], [class*="author"], [class*="user_id"]'
                            );
                            const author = authorEl ? (authorEl.innerText || '').trim() : '';

                            return { content, dateText, starText, productName, reviewId, author };
                        });
                }
            """)

            if not items:
                print(f"[{self.CHANNEL_NAME}] 페이지 {page_num}: 리뷰 없음", flush=True)
                break

            parsed_count = 0
            stop = False
            for item in items:
                try:
                    content = (item.get('content') or '').strip()
                    if len(content) < 15:
                        continue

                    review_date = self._parse_date(item.get('dateText', ''))

                    try:
                        rd = datetime.strptime(review_date, "%Y-%m-%d")
                        if rd < cutoff_date:
                            stop = True
                            break
                    except Exception:
                        pass

                    rating = 5
                    star_text = item.get('starText', '')
                    rm = re.search(r'(\d+)', star_text)
                    if rm:
                        rating = min(5, max(1, int(rm.group(1))))

                    reviews.append({
                        "channel": self.CHANNEL_NAME,
                        "product_name": (item.get('productName') or '').strip(),
                        "option_name": "",
                        "customer_id": (item.get('author') or '').strip(),
                        "order_number": "",
                        "rating": rating,
                        "content": content,
                        "review_date": review_date,
                        "review_id_on_channel": (item.get('reviewId') or '').strip(),
                    })
                    parsed_count += 1
                except Exception:
                    continue

            print(f"[{self.CHANNEL_NAME}] 페이지 {page_num}: {parsed_count}개 파싱 (전체 {len(items)}개 중)", flush=True)

            if stop:
                break

            has_next = self.page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('a'));
                    return btns.some(a =>
                        (a.innerText || '').trim() === '다음' ||
                        (a.className || '').includes('next')
                    );
                }
            """)
            if not has_next:
                break

            page_num += 1
            self.sleep(1.0, 2.0)

            if page_num > 100:
                break
