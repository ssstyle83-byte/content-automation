"""
공통 Playwright 크롤러 베이스 클래스
각 채널 크롤러는 이 클래스를 상속합니다.
"""
import os
import time
import random
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")


class BaseCrawler:
    CHANNEL_NAME = "base"
    LOGIN_URL = ""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self.page: Page = None
        self._session_loaded = False

    @property
    def _session_path(self):
        return os.path.join(SESSION_DIR, f"{self.CHANNEL_NAME}_session.json")

    # ── 브라우저 생명주기 ──────────────────────────────

    def start(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context_kwargs = dict(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ko-KR"
        )
        # 저장된 세션이 있으면 로드
        if os.path.exists(self._session_path):
            try:
                context_kwargs["storage_state"] = self._session_path
                self._session_loaded = True
                print(f"[{self.CHANNEL_NAME}] 저장된 세션 로드")
            except Exception as e:
                print(f"[{self.CHANNEL_NAME}] 세션 로드 실패: {e}")
        self._context = self._browser.new_context(**context_kwargs)
        self.page = self._context.new_page()
        # 봇 감지 우회 기본 설정
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

    def save_session(self):
        """현재 브라우저 세션(쿠키+스토리지)을 파일에 저장."""
        os.makedirs(SESSION_DIR, exist_ok=True)
        self._context.storage_state(path=self._session_path)
        print(f"[{self.CHANNEL_NAME}] 세션 저장 완료: {self._session_path}")

    @classmethod
    def session_exists(cls):
        """저장된 세션 파일이 존재하는지 확인."""
        path = os.path.join(SESSION_DIR, f"{cls.CHANNEL_NAME}_session.json")
        return os.path.exists(path)

    @classmethod
    def delete_session(cls):
        """저장된 세션 파일 삭제."""
        path = os.path.join(SESSION_DIR, f"{cls.CHANNEL_NAME}_session.json")
        if os.path.exists(path):
            os.remove(path)
            print(f"[{cls.CHANNEL_NAME}] 세션 삭제 완료")

    @classmethod
    def manual_login_and_save(cls):
        """
        헤드리스 OFF 브라우저를 열어 사용자가 직접 로그인 후 세션 저장.
        Streamlit 수동 로그인 버튼에서 호출.
        """
        instance = cls(headless=False)
        instance.start()
        try:
            if instance.LOGIN_URL:
                instance.page.goto(instance.LOGIN_URL, wait_until="domcontentloaded")
            instance.page.bring_to_front()  # 창을 최전면으로
            print(f"[{cls.CHANNEL_NAME}] 브라우저가 열렸습니다. 로그인 후 완료를 기다립니다 (최대 5분).")
            success = instance._wait_for_login(timeout=300)
            if success:
                instance.save_session()
                return True
            print(f"[{cls.CHANNEL_NAME}] 로그인 시간 초과")
            return False
        finally:
            instance.close()

    def _wait_for_login(self, timeout: int = 300) -> bool:
        """로그인 완료 대기. 서브클래스에서 오버라이드."""
        time.sleep(min(timeout, 30))
        return True

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

    def _verify_session_login(self) -> bool:
        """저장된 세션 쿠키로 로그인 상태 확인. 대시보드 접근 후 로그인 페이지로 리다이렉트 여부로 판단."""
        if not self.LOGIN_URL:
            return False
        try:
            self.page.goto(self.LOGIN_URL, wait_until="networkidle", timeout=20000)
            self.sleep(1.5, 2.5)
            return not self._is_login_page(self.page.url)
        except Exception:
            return False

    def _is_login_page(self, url: str) -> bool:
        """현재 URL이 로그인 페이지인지 확인. 서브클래스에서 오버라이드 가능."""
        return "login" in url.lower() or "signin" in url.lower()

    # ── 공통 실행 진입점 ──────────────────────────────

    def run_collect(self, days_back: int = 7) -> dict:
        """로그인 후 리뷰+CS 수집. {'reviews': [...], 'cs': [...]} 반환."""
        with self:
            logged_in = False
            # 저장된 세션이 있으면 먼저 세션으로 로그인 시도
            if self._session_loaded:
                logged_in = self._verify_session_login()
                if logged_in:
                    print(f"[{self.CHANNEL_NAME}] 저장된 세션으로 로그인 성공")
                else:
                    print(f"[{self.CHANNEL_NAME}] 저장된 세션 만료 - 자동 로그인 시도")
            # 세션 없거나 만료 → 자동 로그인 시도
            if not logged_in:
                logged_in = self.login()
            if not logged_in:
                return {
                    "reviews": [], "cs": [],
                    "error": "자동 로그인 실패 (사이트 봇 차단). [데이터 수집] 탭에서 '수동 로그인' 버튼으로 한 번만 로그인하면 이후 자동 실행됩니다."
                }
            reviews = self.collect_reviews(days_back)
            cs = self.collect_cs(days_back)
            return {"reviews": reviews, "cs": cs}
