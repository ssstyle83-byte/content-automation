"""
ESM플러스 (G마켓 / 옥션) 크롤러
"""
import os
import re
from datetime import datetime
from .base import BaseCrawler


class ESMPlusCrawler(BaseCrawler):
    CHANNEL_NAME = "ESM플러스"
    LOGIN_URL = "https://signin.esmplus.com/login"
    REVIEW_URL = "https://www.esmplus.com/Sell/Review/ReviewList"
    CS_URL = "https://www.esmplus.com/Sell/Order/ClaimList"

    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.seller_id = os.getenv("ESMPLUS_ID", "")
        self.seller_pw = os.getenv("ESMPLUS_PW", "")

    def login(self) -> bool:
        try:
            self.page.goto(self.LOGIN_URL, wait_until="networkidle")
            self.sleep(1.5, 2.5)

            self.page.fill("input[name='loginId'], #loginId, input[type='text']:first-of-type", self.seller_id)
            self.sleep(0.3, 0.5)
            self.page.fill("input[name='password'], #password, input[type='password']", self.seller_pw)
            self.sleep(0.3, 0.5)
            self.page.click("button[type='submit'], .btn-login, button:has-text('로그인')")
            self.sleep(3, 5)

            return "esmplus.com" in self.page.url and "signin" not in self.page.url
        except Exception as e:
            print(f"[ESMPlus] 로그인 오류: {e}")
            return False

    def collect_reviews(self, days_back: int = 7) -> list:
        reviews = []
        try:
            self.page.goto(self.REVIEW_URL, wait_until="networkidle")
            self.sleep(2, 3)

            start_date, end_date = self.date_range(days_back)
            date_inputs = self.page.query_selector_all("input[type='date'], .datepicker")
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
                rows = self.page.query_selector_all("table tbody tr")
                if not rows:
                    break
                for row in rows:
                    data = self._parse_review_row(row)
                    if data:
                        reviews.append(data)

                next_btn = self.page.query_selector(".paging .next:not(.disable), a.next")
                if not next_btn:
                    break
                next_btn.click()
                self.sleep(1.5, 2.5)
                page_num += 1
                if page_num > 10:
                    break
        except Exception as e:
            print(f"[ESMPlus] 리뷰 수집 오류: {e}")
        return reviews

    def _parse_review_row(self, row) -> object:
        try:
            cells = row.query_selector_all("td")
            if len(cells) < 4:
                return None

            content_el = row.query_selector("[class*='review'], td:nth-child(5)")
            content = content_el.inner_text().strip() if content_el else ""

            rating_el = row.query_selector("[class*='score'], [class*='star']")
            rating_text = rating_el.inner_text() if rating_el else "0"
            rating = int(re.search(r'\d', rating_text).group()) if re.search(r'\d', rating_text) else 0

            product_el = row.query_selector("[class*='product'], td:nth-child(3)")
            product_name = product_el.inner_text().strip() if product_el else ""

            date_el = row.query_selector("[class*='date'], td:last-child")
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
                    title_el = row.query_selector("[class*='claim'], td:nth-child(4)")
                    title = title_el.inner_text().strip() if title_el else ""

                    date_el = row.query_selector("[class*='date'], td:last-child")
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
                        "item_id": f"esm_{inquiry_date}_{len(items)}",
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"[ESMPlus] CS 수집 오류: {e}")
        return items

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        return False  # ESM+ 리뷰 답변 API는 별도 구현 필요

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        return False

    def _normalize_date(self, date_str: str) -> str:
        date_str = date_str.strip()
        m = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', date_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return datetime.now().strftime("%Y-%m-%d")
