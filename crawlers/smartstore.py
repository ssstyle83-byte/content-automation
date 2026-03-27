"""
네이버 스마트스토어 크롤러
- 리뷰 수집 + 주문번호로 실제 고객 아이디 추출
- 리뷰 답변 자동 등록
- CS/문의 수집 및 답변 등록
"""
import os
import re
from datetime import datetime, timedelta
from .base import BaseCrawler


class SmartStoreCrawler(BaseCrawler):
    CHANNEL_NAME = "스마트스토어"
    LOGIN_URL = "https://sell.smartstore.naver.com/#/home/dashboard"
    REVIEW_URL = "https://sell.smartstore.naver.com/#/review/list"
    CS_URL = "https://sell.smartstore.naver.com/#/qna/list"

    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.seller_id = os.getenv("SMARTSTORE_ID", "")
        self.seller_pw = os.getenv("SMARTSTORE_PW", "")

    # ── 로그인 ────────────────────────────────────────

    def login(self) -> bool:
        try:
            self.page.goto("https://nid.naver.com/nidlogin.login", wait_until="networkidle")
            self.sleep(1, 2)

            # 아이디 입력
            self.page.fill("#id", self.seller_id)
            self.sleep(0.3, 0.7)
            self.page.fill("#pw", self.seller_pw)
            self.sleep(0.3, 0.7)
            self.page.click(".btn_login")
            self.sleep(2, 3)

            # 2차 인증 대기 (최대 60초)
            for _ in range(60):
                if "smartstore" in self.page.url or "sell.smartstore" in self.page.url:
                    break
                if "nid.naver.com/login" not in self.page.url and "nid.naver.com/nidlogin" not in self.page.url:
                    break
                self.sleep(1, 1)

            # 판매자센터 접근
            self.page.goto(self.LOGIN_URL, wait_until="networkidle")
            self.sleep(2, 3)
            return "sell.smartstore.naver.com" in self.page.url
        except Exception as e:
            print(f"[SmartStore] 로그인 오류: {e}")
            return False

    # ── 리뷰 수집 ────────────────────────────────────

    def collect_reviews(self, days_back: int = 7) -> list:
        reviews = []
        try:
            self.page.goto(self.REVIEW_URL, wait_until="networkidle")
            self.sleep(2, 3)

            # 날짜 필터 설정 (기간 선택 UI)
            start_date, end_date = self.date_range(days_back)
            self._set_date_filter(start_date, end_date)
            self.sleep(1, 2)

            page_num = 1
            while True:
                rows = self._parse_review_rows()
                if not rows:
                    break
                reviews.extend(rows)

                # 다음 페이지
                next_btn = self.page.query_selector(".pagination .next:not(.disabled)")
                if not next_btn:
                    break
                next_btn.click()
                self.sleep(1.5, 2.5)
                page_num += 1
                if page_num > 20:  # 안전 상한
                    break

        except Exception as e:
            print(f"[SmartStore] 리뷰 수집 오류: {e}")

        return reviews

    def _set_date_filter(self, start_date: str, end_date: str):
        """날짜 필터 입력 (YYYY-MM-DD 형식)."""
        try:
            # 직접 입력 방식 시도
            date_inputs = self.page.query_selector_all("input[type='date'], input.datepicker")
            if len(date_inputs) >= 2:
                date_inputs[0].fill(start_date)
                self.sleep(0.3, 0.5)
                date_inputs[1].fill(end_date)
                self.sleep(0.3, 0.5)
                # 검색 버튼 클릭
                search_btn = self.page.query_selector("button[class*='search'], button:has-text('조회')")
                if search_btn:
                    search_btn.click()
                    self.sleep(1.5, 2.5)
        except Exception as e:
            print(f"[SmartStore] 날짜 필터 설정 오류: {e}")

    def _parse_review_rows(self) -> list:
        rows = []
        try:
            # 리뷰 행 파싱 (스마트스토어 리뷰 테이블 구조)
            review_rows = self.page.query_selector_all("table tbody tr, .review-list-item")
            for row in review_rows:
                try:
                    data = self._extract_review_data(row)
                    if data:
                        rows.append(data)
                except Exception:
                    continue
        except Exception as e:
            print(f"[SmartStore] 리뷰 행 파싱 오류: {e}")
        return rows

    def _extract_review_data(self, row) -> object:
        try:
            # 평점 (별점 이미지 또는 숫자)
            rating_el = row.query_selector(".rating, .star-rating, [class*='rating']")
            rating_text = rating_el.inner_text().strip() if rating_el else ""
            rating = int(re.search(r'\d', rating_text).group()) if re.search(r'\d', rating_text) else 0

            # 리뷰 내용
            content_el = row.query_selector(".review-content, .review-text, td:nth-child(4)")
            content = content_el.inner_text().strip() if content_el else ""

            # 상품명
            product_el = row.query_selector(".product-name, td:nth-child(2)")
            product_name = product_el.inner_text().strip() if product_el else ""

            # 옵션
            option_el = row.query_selector(".option-name, .product-option")
            option_name = option_el.inner_text().strip() if option_el else ""

            # 주문번호 (고객ID 추출에 사용)
            order_el = row.query_selector(".order-number, [class*='order']")
            order_number = order_el.inner_text().strip() if order_el else ""
            order_number = re.sub(r'\D', '', order_number)  # 숫자만 추출

            # 날짜
            date_el = row.query_selector(".review-date, td:nth-child(6)")
            review_date = date_el.inner_text().strip() if date_el else datetime.now().strftime("%Y-%m-%d")
            review_date = self._normalize_date(review_date)

            # 고객 아이디 (별표 처리 → 주문번호로 별도 조회)
            customer_id = ""
            if order_number:
                customer_id = self._get_customer_id_by_order(order_number)

            # 리뷰 ID (답변 등록 시 필요)
            review_id = ""
            link_el = row.query_selector("a[href*='review']")
            if link_el:
                href = link_el.get_attribute("href") or ""
                id_match = re.search(r'[?&]id=(\d+)', href)
                if id_match:
                    review_id = id_match.group(1)

            if not content:
                return None

            return {
                "channel": self.CHANNEL_NAME,
                "product_name": product_name,
                "option_name": option_name,
                "customer_id": customer_id,
                "order_number": order_number,
                "rating": rating,
                "content": content,
                "review_date": review_date,
                "review_id_on_channel": review_id,
            }
        except Exception:
            return None

    def _get_customer_id_by_order(self, order_number: str) -> str:
        """주문번호로 실제 고객 아이디 추출 (별표 처리 해소 핵심 기능)."""
        if not order_number:
            return ""
        try:
            order_url = f"https://sell.smartstore.naver.com/#/order/detail/{order_number}"
            # 새 탭에서 주문 상세 열기
            new_page = self._context.new_page()
            new_page.goto(order_url, wait_until="networkidle")
            self.sleep(1.5, 2.5)

            # 고객 아이디 추출 (구매자 정보 섹션)
            customer_id = ""
            selectors = [
                ".buyer-id", ".orderer-id", "[class*='buyer'] .id",
                "td:has-text('구매자') + td", ".customer-info .id"
            ]
            for sel in selectors:
                el = new_page.query_selector(sel)
                if el:
                    text = el.inner_text().strip()
                    if text and "*" not in text:
                        customer_id = text
                        break

            # 페이지 내 텍스트에서 아이디 패턴 검색
            if not customer_id:
                page_text = new_page.content()
                # 네이버 아이디 패턴: 영문+숫자 조합
                id_patterns = re.findall(r'"buyerId"\s*:\s*"([a-z0-9_]+)"', page_text)
                if id_patterns:
                    customer_id = id_patterns[0]

            new_page.close()
            return customer_id
        except Exception as e:
            print(f"[SmartStore] 고객 아이디 조회 오류 ({order_number}): {e}")
            return ""

    # ── CS/문의 수집 ──────────────────────────────────

    def collect_cs(self, days_back: int = 7) -> list:
        cs_items = []
        try:
            self.page.goto(self.CS_URL, wait_until="networkidle")
            self.sleep(2, 3)

            start_date, end_date = self.date_range(days_back)
            self._set_date_filter(start_date, end_date)
            self.sleep(1, 2)

            page_num = 1
            while True:
                rows = self._parse_cs_rows()
                if not rows:
                    break
                cs_items.extend(rows)

                next_btn = self.page.query_selector(".pagination .next:not(.disabled)")
                if not next_btn:
                    break
                next_btn.click()
                self.sleep(1.5, 2.5)
                page_num += 1
                if page_num > 10:
                    break

        except Exception as e:
            print(f"[SmartStore] CS 수집 오류: {e}")

        return cs_items

    def _parse_cs_rows(self) -> list:
        items = []
        try:
            rows = self.page.query_selector_all("table tbody tr, .qna-list-item")
            for row in rows:
                try:
                    # 제목/내용
                    title_el = row.query_selector(".qna-title, td:nth-child(3)")
                    title = title_el.inner_text().strip() if title_el else ""

                    # 상세 내용은 클릭 후 수집
                    content = title  # 간략 내용은 제목으로 대체

                    # 상품명
                    product_el = row.query_selector(".product-name, td:nth-child(2)")
                    product_name = product_el.inner_text().strip() if product_el else ""

                    # 날짜
                    date_el = row.query_selector(".inquiry-date, td:nth-child(5)")
                    inquiry_date = date_el.inner_text().strip() if date_el else datetime.now().strftime("%Y-%m-%d")
                    inquiry_date = self._normalize_date(inquiry_date)

                    # 문의 아이디 (답변 등록 시 필요)
                    item_id = ""
                    link_el = row.query_selector("a")
                    if link_el:
                        href = link_el.get_attribute("href") or ""
                        id_match = re.search(r'[/=](\d{10,})', href)
                        if id_match:
                            item_id = id_match.group(1)

                    if not title:
                        continue

                    items.append({
                        "channel": self.CHANNEL_NAME,
                        "product_name": product_name,
                        "customer_id": "",
                        "title": title,
                        "content": content,
                        "inquiry_date": inquiry_date,
                        "item_id": item_id or f"ss_{inquiry_date}_{len(items)}",
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"[SmartStore] CS 행 파싱 오류: {e}")
        return items

    # ── 답변 등록 ─────────────────────────────────────

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        try:
            # 리뷰 상세 페이지로 이동
            url = f"https://sell.smartstore.naver.com/#/review/list"
            self.page.goto(url, wait_until="networkidle")
            self.sleep(1.5, 2)

            # 리뷰 ID로 해당 행 찾기
            row = self.page.query_selector(f"[data-review-id='{review_id_on_channel}'], tr[data-id='{review_id_on_channel}']")
            if not row:
                # 검색으로 찾기
                print(f"[SmartStore] 리뷰 ID {review_id_on_channel} 직접 접근 시도")
                return self._post_reply_via_search(review_id_on_channel, reply_text)

            # 답변 버튼 클릭
            reply_btn = row.query_selector("button:has-text('답변'), .reply-btn")
            if reply_btn:
                reply_btn.click()
                self.sleep(1, 1.5)

            # 답변 입력
            textarea = self.page.query_selector("textarea.reply-input, .reply-area textarea")
            if not textarea:
                return False
            textarea.fill(reply_text)
            self.sleep(0.5, 1)

            # 등록 버튼
            submit_btn = self.page.query_selector("button:has-text('등록'), button:has-text('저장')")
            if submit_btn:
                submit_btn.click()
                self.sleep(1.5, 2)
                return True
        except Exception as e:
            print(f"[SmartStore] 리뷰 답변 등록 오류: {e}")
        return False

    def _post_reply_via_search(self, review_id: str, reply_text: str) -> bool:
        """리뷰를 직접 검색하여 답변 등록."""
        try:
            # 리뷰 페이지에서 ID로 검색
            self.page.goto(
                f"https://sell.smartstore.naver.com/#/review/detail/{review_id}",
                wait_until="networkidle"
            )
            self.sleep(1.5, 2.5)

            textarea = self.page.query_selector("textarea, .reply-input")
            if not textarea:
                return False
            textarea.fill(reply_text)
            self.sleep(0.5, 1)

            submit_btn = self.page.query_selector("button:has-text('등록'), button[type='submit']")
            if submit_btn:
                submit_btn.click()
                self.sleep(1.5, 2)
                return True
        except Exception as e:
            print(f"[SmartStore] 검색 답변 등록 오류: {e}")
        return False

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        try:
            self.page.goto(
                f"https://sell.smartstore.naver.com/#/qna/detail/{cs_id_on_channel}",
                wait_until="networkidle"
            )
            self.sleep(1.5, 2.5)

            textarea = self.page.query_selector("textarea, .answer-input")
            if not textarea:
                return False
            textarea.fill(reply_text)
            self.sleep(0.5, 1)

            submit_btn = self.page.query_selector("button:has-text('등록'), button:has-text('답변'), button[type='submit']")
            if submit_btn:
                submit_btn.click()
                self.sleep(1.5, 2)
                return True
        except Exception as e:
            print(f"[SmartStore] CS 답변 등록 오류: {e}")
        return False

    # ── 유틸 ──────────────────────────────────────────

    def _normalize_date(self, date_str: str) -> str:
        """다양한 날짜 형식을 YYYY-MM-DD로 정규화."""
        date_str = date_str.strip()
        patterns = [
            (r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', '{}-{:02d}-{:02d}'),
            (r'(\d{4})(\d{2})(\d{2})', '{}-{}-{}'),
        ]
        for pattern, fmt in patterns:
            m = re.search(pattern, date_str)
            if m:
                g = m.groups()
                try:
                    return fmt.format(int(g[0]), int(g[1]), int(g[2]))
                except Exception:
                    pass
        return datetime.now().strftime("%Y-%m-%d")
