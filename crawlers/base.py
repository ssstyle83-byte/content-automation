"""
공통 Playwright 크롤러 베이스 클래스
각 채널 크롤러는 이 클래스를 상속합니다.
"""
import os
import time
import random
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext


class BaseCrawler:
    CHANNEL_NAME = "base"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self.page: Page = None

    # ── 브라우저 생명주기 ──────────────────────────────

    def start(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ko-KR"
        )
        self.page = self._context.new_page()
        # 봇 감지 우회 기본 설정
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    # ── 유틸 메서드 ──────────────────────────────────

    def sleep(self, min_sec: float = 0.8, max_sec: float = 2.0):
        """사람처럼 랜덤 딜레이."""
        time.sleep(random.uniform(min_sec, max_sec))

    def wait_and_click(self, selector: str, timeout: int = 10000):
        self.page.wait_for_selector(selector, timeout=timeout)
        self.page.click(selector)
        self.sleep(0.5, 1.2)

    def safe_text(self, selector: str, default: str = "") -> str:
        try:
            el = self.page.query_selector(selector)
            return el.inner_text().strip() if el else default
        except Exception:
            return default

    def safe_attr(self, selector: str, attr: str, default: str = "") -> str:
        try:
            el = self.page.query_selector(selector)
            return el.get_attribute(attr) or default if el else default
        except Exception:
            return default

    def date_range(self, days_back: int = 7):
        """오늘부터 days_back일 전까지의 날짜 범위 반환."""
        end = datetime.now()
        start = end - timedelta(days=days_back)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    # ── 서브클래스가 구현해야 할 메서드 ──────────────────

    def login(self) -> bool:
        raise NotImplementedError

    def collect_reviews(self, days_back: int = 7) -> list:
        """리뷰 데이터 수집. 각 채널 크롤러가 구현."""
        raise NotImplementedError

    def collect_cs(self, days_back: int = 7) -> list:
        """CS/문의 데이터 수집. 각 채널 크롤러가 구현."""
        raise NotImplementedError

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        """채널에 리뷰 답변 등록. 각 채널 크롤러가 구현."""
        raise NotImplementedError

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        """채널에 CS 답변 등록. 각 채널 크롤러가 구현."""
        raise NotImplementedError

    # ── 공통 실행 진입점 ──────────────────────────────

    def run_collect(self, days_back: int = 7) -> dict:
        """로그인 후 리뷰+CS 수집. {'reviews': [...], 'cs': [...]} 반환."""
        with self:
            if not self.login():
                return {"reviews": [], "cs": [], "error": "로그인 실패"}
            reviews = self.collect_reviews(days_back)
            cs = self.collect_cs(days_back)
            return {"reviews": reviews, "cs": cs}
