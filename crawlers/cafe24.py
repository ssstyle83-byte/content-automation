"""
카페24 자사몰 크롤러
"""
import os
import re
from datetime import datetime
from .base import BaseCrawler


class Cafe24Crawler(BaseCrawler):
    CHANNEL_NAME = "카페24"
    BASE_URL = "https://eclogin.cafe24.com/Shop/"

    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.mall_id = os.getenv("CAFE24_MALL_ID", "")
        self.seller_id = os.getenv("CAFE24_ID", "")
        self.seller_pw = os.getenv("CAFE24_PW", "")

    def login(self) -> bool:
        try:
            login_url = f"https://{self.mall_id}.cafe24.com/admin/php/login.php" if self.mall_id else self.BASE_URL
            self.page.goto(login_url, wait_until="networkidle")
            self.sleep(1.5, 2.5)

            # 쇼핑몰 ID 입력 (필요 시)
            mall_input = self.page.query_selector("input[name='mall_id'], #mall_id")
            if mall_input and self.mall_id:
                mall_input.fill(self.mall_id)
                self.sleep(0.3, 0.5)

            self.page.fill("input[name='user_id'], #user_id", self.seller_id)
            self.sleep(0.3, 0.5)
            self.page.fill("input[name='passwd'], #passwd, input[type='password']", self.seller_pw)
            self.sleep(0.3, 0.5)
            self.page.click("button[type='submit'], input[type='submit'], .btn_submit")
            self.sleep(2, 3)

            return "admin" in self.page.url or "cafe24" in self.page.url
        except Exception as e:
            print(f"[Cafe24] 로그인 오류: {e}")
            return False

    def collect_reviews(self, days_back: int = 7) -> list:
        reviews = []
        try:
            # 카페24 관리자 - 상품 후기 관리
            review_url = f"https://{self.mall_id}.cafe24.com/admin/php/shop1/b_product_review_list.php" if self.mall_id \
                else "https://eclogin.cafe24.com/Shop/?controller=product_review"
            self.page.goto(review_url, wait_until="networkidle")
            self.sleep(2, 3)

            start_date, end_date = self.date_range(days_back)

            # 날짜 필터
            date_inputs = self.page.query_selector_all("input[name*='date'], input[type='date']")
            if len(date_inputs) >= 2:
                date_inputs[0].fill(start_date.replace("-", ""))
                self.sleep(0.3, 0.5)
                date_inputs[1].fill(end_date.replace("-", ""))
                self.sleep(0.3, 0.5)

            search_btn = self.page.query_selector("button:has-text('검색'), input[value='검색']")
            if search_btn:
                search_btn.click()
                self.sleep(1.5, 2.5)

            rows = self.page.query_selector_all("table tbody tr")
            for row in rows:
                data = self._parse_review_row(row)
                if data:
                    reviews.append(data)

        except Exception as e:
            print(f"[Cafe24] 리뷰 수집 오류: {e}")
        return reviews

    def _parse_review_row(self, row) -> object:
        try:
            cells = row.query_selector_all("td")
            if len(cells) < 4:
                return None

            content_el = row.query_selector(".review_content, td:nth-child(5)")
            content = content_el.inner_text().strip() if content_el else ""

            rating_el = row.query_selector(".rating, [class*='star']")
            rating_text = rating_el.inner_text() if rating_el else "0"
            rating = int(re.search(r'\d', rating_text).group()) if re.search(r'\d', rating_text) else 0

            product_el = row.query_selector(".product_name, td:nth-child(3)")
            product_name = product_el.inner_text().strip() if product_el else ""

            date_el = row.query_selector(".reg_date, td:last-child")
            review_date = date_el.inner_text().strip() if date_el else datetime.now().strftime("%Y-%m-%d")
            review_date = self._normalize_date(review_date)

            customer_el = row.query_selector(".member_id, td:nth-child(2)")
            customer_id = customer_el.inner_text().strip() if customer_el else ""

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
                "review_id_on_channel": "",
            }
        except Exception:
            return None

    def collect_cs(self, days_back: int = 7) -> list:
        items = []
        try:
            cs_url = f"https://{self.mall_id}.cafe24.com/admin/php/shop1/b_board_list.php" if self.mall_id \
                else "https://eclogin.cafe24.com/Shop/?controller=inquiry"
            self.page.goto(cs_url, wait_until="networkidle")
            self.sleep(2, 3)

            rows = self.page.query_selector_all("table tbody tr")
            for row in rows:
                try:
                    title_el = row.query_selector(".board_title, td:nth-child(3)")
                    title = title_el.inner_text().strip() if title_el else ""

                    date_el = row.query_selector(".reg_date, td:last-child")
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
                        "item_id": f"c24_{inquiry_date}_{len(items)}",
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"[Cafe24] CS 수집 오류: {e}")
        return items

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        try:
            reply_url = f"https://{self.mall_id}.cafe24.com/admin/php/shop1/b_product_review_detail.php?review_no={review_id_on_channel}"
            self.page.goto(reply_url, wait_until="networkidle")
            self.sleep(1.5, 2)

            textarea = self.page.query_selector("textarea[name*='reply'], .reply_content")
            if not textarea:
                return False
            textarea.fill(reply_text)
            self.sleep(0.5, 1)

            submit = self.page.query_selector("button:has-text('저장'), input[value='저장']")
            if submit:
                submit.click()
                self.sleep(1.5, 2)
                return True
        except Exception as e:
            print(f"[Cafe24] 리뷰 답변 오류: {e}")
        return False

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        return False  # 카페24 문의 답변은 채널마다 구조 상이 → 추후 구현

    def _normalize_date(self, date_str: str) -> str:
        date_str = date_str.strip()
        m = re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', date_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        m2 = re.search(r'(\d{4})(\d{2})(\d{2})', date_str)
        if m2:
            return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
        return datetime.now().strftime("%Y-%m-%d")
