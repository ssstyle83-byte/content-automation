"""
11번가 셀러오피스 크롤러
"""
import os
import re
from datetime import datetime
from .base import BaseCrawler


class ElevenCrawler(BaseCrawler):
    CHANNEL_NAME = "11번가"
    LOGIN_URL = "https://login.11st.co.kr/auth/front/selleroffice/login.tmall"
    REVIEW_URL = "https://soffice.11st.co.kr/view/review/reviewMgmtList"
    CS_URL = "https://soffice.11st.co.kr/view/claim/claimList"

    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.seller_id = os.getenv("ELEVEN_ID", "")
        self.seller_pw = os.getenv("ELEVEN_PW", "")

    def login(self) -> bool:
        try:
            self.page.goto(self.LOGIN_URL, wait_until="networkidle")
            self.sleep(1.5, 2.5)

            self.page.fill("input[name='sellerId'], #sellerId, input[type='text']", self.seller_id)
            self.sleep(0.3, 0.5)
            self.page.fill("input[name='sellerPwd'], #sellerPwd, input[type='password']", self.seller_pw)
            self.sleep(0.3, 0.5)
            self.page.click("button[type='submit'], .btn_login, a.btn_login")
            self.sleep(3, 5)

            return "soffice.11st.co.kr" in self.page.url
        except Exception as e:
            print(f"[11번가] 로그인 오류: {e}")
            return False

    def collect_reviews(self, days_back: int = 7) -> list:
        reviews = []
        try:
            self.page.goto(self.REVIEW_URL, wait_until="networkidle")
            self.sleep(2, 3)

            start_date, end_date = self.date_range(days_back)
            date_inputs = self.page.query_selector_all("input.inp_calendar, input[type='date']")
            if len(date_inputs) >= 2:
                date_inputs[0].fill(start_date.replace("-", "."))
                self.sleep(0.3, 0.5)
                date_inputs[1].fill(end_date.replace("-", "."))
                self.sleep(0.3, 0.5)

            search_btn = self.page.query_selector("button:has-text('조회'), a.btn_search")
            if search_btn:
                search_btn.click()
                self.sleep(2, 3)

            page_num = 1
            while True:
                rows = self.page.query_selector_all("table.tbl_list tbody tr, .review_list li")
                if not rows:
                    break
                for row in rows:
                    data = self._parse_review_row(row)
                    if data:
                        reviews.append(data)

                next_btn = self.page.query_selector(".paging a.next:not(.disabled)")
                if not next_btn:
                    break
                next_btn.click()
                self.sleep(1.5, 2.5)
                page_num += 1
                if page_num > 10:
                    break
        except Exception as e:
            print(f"[11번가] 리뷰 수집 오류: {e}")
        return reviews

    def _parse_review_row(self, row) -> object:
        try:
            content_el = row.query_selector(".review_txt, td.td_review, td:nth-child(5)")
            content = content_el.inner_text().strip() if content_el else ""

            rating_el = row.query_selector(".star_score, [class*='rating']")
            rating_text = rating_el.inner_text() if rating_el else "0"
            rating = int(re.search(r'\d', rating_text).group()) if re.search(r'\d', rating_text) else 0

            product_el = row.query_selector(".prd_name, td:nth-child(2)")
            product_name = product_el.inner_text().strip() if product_el else ""

            date_el = row.query_selector(".review_date, td.td_date")
            review_date = date_el.inner_text().strip() if date_el else datetime.now().strftime("%Y-%m-%d")
            review_date = self._normalize_date(review_date)

            if not content:
                return None

            return {
                "channel": self.CHANNEL_NAME,
                "product_name": product_name,
                "option_name": "",
                "customer_id": "",
                "order_number": "",
                "rating": rating,
                "content": content,
                "review_date": review_date,
                "review_id_on_channel": "",
            }
        except Exception:
            return None

    def collect_cs(self, days_back: int = 7) -> list:
        items = []
        try:
            self.page.goto(self.CS_URL, wait_until="networkidle")
            self.sleep(2, 3)

            rows = self.page.query_selector_all("table tbody tr")
            for row in rows:
                try:
                    title_el = row.query_selector("td:nth-child(4), .claim_type")
                    title = title_el.inner_text().strip() if title_el else ""

                    date_el = row.query_selector("td.td_date, td:last-child")
                    inquiry_date = date_el.inner_text().strip() if date_el else datetime.now().strftime("%Y-%m-%d")
                    inquiry_date = self._normalize_date(inquiry_date)

                    if not title:
                        continue

                    items.append({
                        "channel": self.CHANNEL_NAME,
                        "product_name": "",
                        "customer_id": "",
                        "title": title,
                        "content": title,
                        "inquiry_date": inquiry_date,
                        "item_id": f"11st_{inquiry_date}_{len(items)}",
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"[11번가] CS 수집 오류: {e}")
        return items

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        return False  # 추후 구현

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        return False

    def _normalize_date(self, date_str: str) -> str:
        date_str = date_str.strip()
        m = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', date_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return datetime.now().strftime("%Y-%m-%d")
