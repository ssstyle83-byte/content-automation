"""
쿠팡 Wing 크롤러
"""
import os
import re
from datetime import datetime
from .base import BaseCrawler


class CoupangCrawler(BaseCrawler):
    CHANNEL_NAME = "쿠팡"
    LOGIN_URL = "https://wing.coupang.com/sso/login"
    REVIEW_URL = "https://wing.coupang.com/vendor-review/list"
    CS_URL = "https://wing.coupang.com/vendor-inquiries/list"

    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.seller_id = os.getenv("COUPANG_ID", "")
        self.seller_pw = os.getenv("COUPANG_PW", "")

    def login(self) -> bool:
        try:
            self.page.goto(
                "https://xauth.coupang.com/auth/realms/seller/protocol/openid-connect/auth"
                "?response_type=code&client_id=wing&redirect_uri=https://wing.coupang.com/sso/login"
                "?returnUrl=https://wing.coupang.com/&state=login&login=true&scope=openid",
                wait_until="networkidle"
            )
            self.sleep(1.5, 2.5)

            self.page.fill("input[name='username'], #username", self.seller_id)
            self.sleep(0.3, 0.6)
            self.page.fill("input[name='password'], #password", self.seller_pw)
            self.sleep(0.3, 0.6)
            self.page.click("button[type='submit'], .login-btn")
            self.sleep(3, 5)

            # 2차 인증 대기 (최대 60초)
            for _ in range(60):
                if "wing.coupang.com" in self.page.url and "xauth" not in self.page.url:
                    return True
                self.sleep(1, 1)
            return False
        except Exception as e:
            print(f"[Coupang] 로그인 오류: {e}")
            return False

    def collect_reviews(self, days_back: int = 7) -> list:
        reviews = []
        try:
            self.page.goto(self.REVIEW_URL, wait_until="networkidle")
            self.sleep(2, 3)

            start_date, end_date = self.date_range(days_back)

            # 날짜 필터
            date_inputs = self.page.query_selector_all("input[type='date'], .date-picker input")
            if len(date_inputs) >= 2:
                date_inputs[0].fill(start_date)
                self.sleep(0.3, 0.5)
                date_inputs[1].fill(end_date)
                self.sleep(0.3, 0.5)

            search_btn = self.page.query_selector("button:has-text('조회'), button:has-text('검색')")
            if search_btn:
                search_btn.click()
                self.sleep(2, 3)

            page_num = 1
            while True:
                rows = self.page.query_selector_all("table tbody tr, .review-item")
                if not rows:
                    break
                for row in rows:
                    data = self._parse_review_row(row)
                    if data:
                        reviews.append(data)

                next_btn = self.page.query_selector(".pagination .next:not(.disabled), button.next:not([disabled])")
                if not next_btn:
                    break
                next_btn.click()
                self.sleep(1.5, 2.5)
                page_num += 1
                if page_num > 20:
                    break
        except Exception as e:
            print(f"[Coupang] 리뷰 수집 오류: {e}")
        return reviews

    def _parse_review_row(self, row) -> object:
        try:
            rating_el = row.query_selector("[class*='rating'], [class*='star']")
            rating_text = rating_el.inner_text() if rating_el else "0"
            rating = int(re.search(r'\d', rating_text).group()) if re.search(r'\d', rating_text) else 0

            content_el = row.query_selector("[class*='content'], [class*='review-text'], td:nth-child(5)")
            content = content_el.inner_text().strip() if content_el else ""

            product_el = row.query_selector("[class*='product'], td:nth-child(2)")
            product_name = product_el.inner_text().strip() if product_el else ""

            option_el = row.query_selector("[class*='option'], td:nth-child(3)")
            option_name = option_el.inner_text().strip() if option_el else ""

            date_el = row.query_selector("[class*='date'], td:last-child")
            review_date = date_el.inner_text().strip() if date_el else datetime.now().strftime("%Y-%m-%d")
            review_date = self._normalize_date(review_date)

            order_el = row.query_selector("[class*='order'], td:nth-child(4)")
            order_number = re.sub(r'\D', '', order_el.inner_text()) if order_el else ""

            if not content:
                return None

            return {
                "channel": self.CHANNEL_NAME,
                "product_name": product_name,
                "option_name": option_name,
                "customer_id": "",
                "order_number": order_number,
                "rating": rating,
                "content": content,
                "review_date": review_date,
                "review_id_on_channel": order_number,
            }
        except Exception:
            return None

    def collect_cs(self, days_back: int = 7) -> list:
        items = []
        try:
            self.page.goto(self.CS_URL, wait_until="networkidle")
            self.sleep(2, 3)

            rows = self.page.query_selector_all("table tbody tr, .inquiry-item")
            for row in rows:
                try:
                    title_el = row.query_selector("[class*='title'], td:nth-child(3)")
                    title = title_el.inner_text().strip() if title_el else ""

                    product_el = row.query_selector("[class*='product'], td:nth-child(2)")
                    product_name = product_el.inner_text().strip() if product_el else ""

                    date_el = row.query_selector("[class*='date'], td:last-child")
                    inquiry_date = date_el.inner_text().strip() if date_el else datetime.now().strftime("%Y-%m-%d")
                    inquiry_date = self._normalize_date(inquiry_date)

                    if not title:
                        continue

                    items.append({
                        "channel": self.CHANNEL_NAME,
                        "product_name": product_name,
                        "customer_id": "",
                        "title": title,
                        "content": title,
                        "inquiry_date": inquiry_date,
                        "item_id": f"cp_{inquiry_date}_{len(items)}",
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"[Coupang] CS 수집 오류: {e}")
        return items

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        try:
            self.page.goto(self.REVIEW_URL, wait_until="networkidle")
            self.sleep(1.5, 2)

            # 해당 리뷰 행에서 답변 버튼 찾기
            row = self.page.query_selector(f"[data-id='{review_id_on_channel}']")
            if row:
                btn = row.query_selector("button:has-text('답변'), .reply-btn")
                if btn:
                    btn.click()
                    self.sleep(1, 1.5)

            textarea = self.page.query_selector("textarea.reply, .reply-input")
            if not textarea:
                return False
            textarea.fill(reply_text)
            self.sleep(0.5, 1)

            submit = self.page.query_selector("button:has-text('등록'), button[type='submit']")
            if submit:
                submit.click()
                self.sleep(1.5, 2)
                return True
        except Exception as e:
            print(f"[Coupang] 리뷰 답변 오류: {e}")
        return False

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        try:
            self.page.goto(f"{self.CS_URL}?id={cs_id_on_channel}", wait_until="networkidle")
            self.sleep(1.5, 2)

            textarea = self.page.query_selector("textarea")
            if not textarea:
                return False
            textarea.fill(reply_text)
            self.sleep(0.5, 1)

            submit = self.page.query_selector("button:has-text('등록'), button[type='submit']")
            if submit:
                submit.click()
                self.sleep(1.5, 2)
                return True
        except Exception as e:
            print(f"[Coupang] CS 답변 오류: {e}")
        return False

    def _normalize_date(self, date_str: str) -> str:
        date_str = date_str.strip()
        m = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', date_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return datetime.now().strftime("%Y-%m-%d")
