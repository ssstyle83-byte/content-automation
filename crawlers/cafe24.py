from __future__ import annotations

from datetime import datetime, timedelta
import re

from .base import BaseCrawler
from .meditial_sources import CAFE24_PRODUCT_URLS


class Cafe24Crawler(BaseCrawler):
    CHANNEL_NAME = "카페24"
    LOGIN_URL = ""
    PRODUCT_URLS = CAFE24_PRODUCT_URLS

    def login(self) -> bool:
        return True

    def collect_cs(self, days_back: int = 7) -> list:
        return []

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        return False

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        return False

    def _normalize_date(self, text: str) -> str:
        m = re.search(r"(\\d{4})[./-](\\d{1,2})[./-](\\d{1,2})", text or "")
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return datetime.now().strftime("%Y-%m-%d")

    def collect_reviews(self, days_back: int = 7) -> list:
        reviews = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        for url in self.PRODUCT_URLS:
            try:
                self.page.goto(url, timeout=30000)
                self.sleep(2.0, 3.0)

                product_name = self.page.title()
                product_id = re.search(r"/(\\d+)", url).group(1)

                items = self.page.evaluate("""
                    () => {
                        const results = [];
                        const nodes = document.querySelectorAll("li, div");

                        nodes.forEach(el => {
                            const text = el.innerText || "";
                            if (text.length < 20) return;

                            results.push({
                                content: text,
                                dateStr: text,
                                rating: 5,
                                reviewId: el.getAttribute("data-review-id") || ""
                            });
                        });

                        return results;
                    }
                """)

                for idx, item in enumerate(items):
                    review_date = self._normalize_date(item["dateStr"])

                    if datetime.strptime(review_date, "%Y-%m-%d") < cutoff_date:
                        continue

                    reviews.append({
                        "channel": self.CHANNEL_NAME,
                        "product_name": product_name,
                        "rating": item["rating"],
                        "content": item["content"],
                        "review_date": review_date,
                        "review_id_on_channel": item["reviewId"] or f"{product_id}_{idx}"
                    })

            except Exception as e:
                print("카페24 수집 오류:", e)

        return reviews