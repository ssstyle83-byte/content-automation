from __future__ import annotations

import os
import re
import tempfile
import time
from datetime import datetime, timedelta

import pandas as pd

from .base import BaseCrawler


class SmartStoreCrawler(BaseCrawler):
    CHANNEL_NAME = "스마트스토어"
    LOGIN_URL = "https://sell.smartstore.naver.com/"
    ADMIN_REVIEW_URL = "https://sell.smartstore.naver.com/#/review/search"

    # ── 로그인 ────────────────────────────────────────

    def login(self) -> bool:
        seller_id = os.getenv("SMARTSTORE_ID", "").strip()
        seller_pw = os.getenv("SMARTSTORE_PW", "").strip()

        if not seller_id or not seller_pw:
            print(
                f"[{self.CHANNEL_NAME}] SMARTSTORE_ID / SMARTSTORE_PW 미설정 — 수동 로그인 필요",
                flush=True,
            )
            return False

        try:
            print(f"[{self.CHANNEL_NAME}] 자동 로그인 시도: {seller_id}", flush=True)
            self.page.goto(
                "https://nid.naver.com/nidlogin.login?mode=form&url=https://sell.smartstore.naver.com/",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            self.sleep(1.5, 2.5)

            id_input = self.page.query_selector("#id") or self.page.query_selector("input[name='id']")
            if id_input:
                id_input.click()
                id_input.fill(seller_id)
                self.sleep(0.3, 0.7)
            else:
                print(f"[{self.CHANNEL_NAME}] ID 입력 필드 없음", flush=True)
                return False

            pw_input = self.page.query_selector("#pw") or self.page.query_selector("input[name='pw']")
            if pw_input:
                pw_input.click()
                pw_input.fill(seller_pw)
                self.sleep(0.3, 0.7)
            else:
                print(f"[{self.CHANNEL_NAME}] PW 입력 필드 없음", flush=True)
                return False

            login_btn = (
                self.page.query_selector("#log\\.login")
                or self.page.query_selector("button[type='submit']")
                or self.page.query_selector(".btn_login")
            )
            if login_btn:
                login_btn.click()
            else:
                self.page.keyboard.press("Enter")

            self.sleep(3.0, 5.0)
            current_url = self.page.url
            print(f"[{self.CHANNEL_NAME}] 로그인 후 URL: {current_url}", flush=True)

            if "nid.naver.com" in current_url:
                print(
                    f"[{self.CHANNEL_NAME}] 자동 로그인 실패 (CAPTCHA/OTP). 수동 로그인 버튼을 이용하세요.",
                    flush=True,
                )
                return False

            print(f"[{self.CHANNEL_NAME}] 자동 로그인 성공", flush=True)
            return True

        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 로그인 오류: {e}", flush=True)
            return False

    def _is_login_page(self, url: str) -> bool:
        """URL 또는 페이지 내용으로 로그인 화면 여부 판단."""
        if "nid.naver.com" in url:
            return True
        # 스마트스토어 자체 로그인 페이지 감지 (같은 도메인이라 URL만으론 판단 불가)
        try:
            body = self.page.evaluate("() => document.body.innerText || ''")
            for indicator in [
                "네이버 커머스 ID로 로그인",
                "이메일/판매자 아이디로 로그인",
                "로그인해 주세요",
                "네이버 아이디로 로그인",
            ]:
                if indicator in body:
                    return True
        except Exception:
            pass
        return False

    def _wait_for_login(self, timeout: int = 300) -> bool:
        """수동 로그인 완료 대기 — 어드민 콘텐츠 진입 여부로 확인."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                body = self.page.evaluate("() => document.body.innerText || ''")
                if "리뷰" in body and "로그인해 주세요" not in body:
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    # ── 인터페이스 충족 ───────────────────────────────

    def collect_cs(self, days_back: int = 7) -> list:
        return []

    def post_review_reply(self, review_id_on_channel: str, reply_text: str) -> bool:
        return False

    def post_cs_reply(self, cs_id_on_channel: str, reply_text: str) -> bool:
        return False

    # ── 리뷰 수집 (엑셀 다운로드) ──────────────────────

    def collect_reviews(self, days_back: int = 7) -> list:
        cutoff_date = datetime.now() - timedelta(days=days_back)
        start_str = cutoff_date.strftime("%Y.%m.%d")
        end_str = datetime.now().strftime("%Y.%m.%d")

        print(
            f"[{self.CHANNEL_NAME}] 리뷰 수집 시작 ({start_str} ~ {end_str})",
            flush=True,
        )

        try:
            # 어드민 홈으로 먼저 이동 (세션/로그인 확인)
            self.page.goto(self.LOGIN_URL, wait_until="networkidle", timeout=40000)
            self.sleep(3.0, 5.0)
            print(f"[{self.CHANNEL_NAME}] 어드민 홈 진입: {self.page.url}", flush=True)

            # 세션 만료 또는 로그인 화면인지 확인
            if self._is_login_page(self.page.url):
                print(f"[{self.CHANNEL_NAME}] 세션 만료 감지 — 자동 로그인 재시도", flush=True)
                if not self.login():
                    print(
                        f"[{self.CHANNEL_NAME}] 재로그인 실패. 수동 로그인 버튼을 이용하세요.",
                        flush=True,
                    )
                    return []
                self.page.goto(self.LOGIN_URL, wait_until="networkidle", timeout=30000)
                self.sleep(3.0, 5.0)

            # 사이드바 메뉴 클릭으로 리뷰 관리 페이지로 이동
            # (goto('#/review/search') 직접 접근 시 Angular 폼 미렌더링 문제 우회)
            nav_ok = self._navigate_to_review_page()
            if not nav_ok:
                print(f"[{self.CHANNEL_NAME}] 메뉴 클릭 실패 — fallback: 직접 URL 이동", flush=True)
                self.page.goto(self.ADMIN_REVIEW_URL, wait_until="networkidle", timeout=30000)
                self.sleep(8.0, 10.0)
                self._wait_for_page_ready()

            self._set_date_range(start_str, end_str, days_back)
            self._click_search()
            self.sleep(3.0, 4.0)

            reviews = self._download_excel_and_parse(cutoff_date)
            print(f"[{self.CHANNEL_NAME}] 총 {len(reviews)}건 수집 완료", flush=True)
            return reviews

        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 수집 오류: {e}", flush=True)
            return []

    def _dismiss_modals(self) -> None:
        """어드민 홈 진입 시 나타나는 팝업/모달을 닫아 클릭 차단 해제."""
        try:
            modal = self.page.locator(".modal.in, .modal.show")
            if modal.count() == 0:
                return
            print(f"[{self.CHANNEL_NAME}] 모달 감지 ({modal.count()}개) — 닫기 시도", flush=True)
        except Exception:
            return

        # 닫기 버튼 후보 (selector 순서대로 시도)
        close_selectors = [
            ".modal.in button.close",
            ".modal.in button[data-dismiss='modal']",
            ".modal.in .btn-close",
            ".modal.in button:has-text('닫기')",
            ".modal.in button:has-text('확인')",
            ".modal.in button:has-text('오늘 하루 보지 않기')",
            "button.close",
        ]
        for sel in close_selectors:
            try:
                btn = self.page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    print(f"[{self.CHANNEL_NAME}] 모달 닫기 성공: {sel}", flush=True)
                    self.sleep(0.5, 1.0)
                    return
            except Exception:
                continue

        # 닫기 버튼 못 찾으면 ESC
        try:
            self.page.keyboard.press("Escape")
            self.sleep(0.3, 0.7)
            print(f"[{self.CHANNEL_NAME}] 모달 ESC로 닫기 시도", flush=True)
        except Exception:
            pass

    def _navigate_to_review_page(self) -> bool:
        """Angular 라우터를 정상 트리거해서 리뷰 검색 폼 진입.

        문제: text=리뷰관리 로케이터가 서브메뉴 대신 상위 메뉴("문의/리뷰관리")를
              다시 클릭해 URL이 dashboard에 머무름.
        해결: 상위 메뉴 클릭 후 JS window.location.hash 변경으로 Angular 라우터 직접 트리거.
        """
        try:
            # Step 1: 모달 닫기 (포인터 이벤트 차단 해제)
            self._dismiss_modals()

            # Step 2: "문의/리뷰관리" 클릭 — Angular 앱이 활성 상태임을 확인
            menu_loc = self.page.locator("text=문의/리뷰관리")
            if menu_loc.count() > 0:
                try:
                    menu_loc.first.click(timeout=10000)
                except Exception:
                    self.page.evaluate("(el) => el.click()", menu_loc.first.element_handle())
                print(f"[{self.CHANNEL_NAME}] '문의/리뷰관리' 클릭", flush=True)
                self.sleep(1.0, 1.5)
            else:
                print(f"[{self.CHANNEL_NAME}] '문의/리뷰관리' 메뉴 없음 — JS 해시 이동만 시도", flush=True)

            # Step 3: JS로 hash 변경 → Angular hashchange 이벤트 → route component 렌더링
            # page.goto()와 달리 이미 로드된 Angular 앱에서 hash를 바꾸면 라우터가 정상 동작함
            self.page.evaluate("window.location.hash = '/review/search'")
            print(f"[{self.CHANNEL_NAME}] JS hash → /review/search", flush=True)
            self.sleep(2.0, 3.0)

            # Step 4: 리뷰 검색 폼 렌더링 대기
            self._wait_for_page_ready()
            print(f"[{self.CHANNEL_NAME}] 리뷰 페이지 URL: {self.page.url}", flush=True)

            if "#/review" in self.page.url:
                return True

            print(f"[{self.CHANNEL_NAME}] URL이 리뷰 페이지로 변경되지 않음", flush=True)
            return False

        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 메뉴 네비게이션 오류: {e}", flush=True)
            return False

    def _wait_for_page_ready(self) -> None:
        """Angular SPA 리뷰 검색 폼이 완전히 렌더링될 때까지 대기.

        '엑셀다운' 텍스트는 상단 nav에 없고 리뷰 검색 폼에만 존재하므로
        이 텍스트가 나타날 때 폼 준비 완료로 판단.
        """
        # 리뷰 검색 폼 전용 키워드 (상단 nav에는 없는 텍스트)
        form_keywords = ["엑셀다운", "엑셀 다운", "엑셀다운로드", "리뷰목록", "리뷰 목록"]
        for keyword in form_keywords:
            try:
                self.page.wait_for_function(
                    f"() => document.body.innerText.includes('{keyword}')",
                    timeout=20000,
                )
                print(f"[{self.CHANNEL_NAME}] 페이지 준비 완료 ('{keyword}' 감지)", flush=True)
                # 폼 렌더링 후 추가 안정화 대기
                self.sleep(1.0, 2.0)
                return
            except Exception:
                continue

        # 모두 실패 시 현재 페이지 텍스트 진단 로그
        try:
            body = self.page.evaluate("() => document.body.innerText || ''")
            print(f"[{self.CHANNEL_NAME}] 페이지 준비 timeout. 텍스트 샘플: {body[:300]}", flush=True)
        except Exception:
            pass
        # 추가 대기 후 진행
        self.sleep(3.0, 5.0)

    # ── 날짜 범위 설정 ────────────────────────────────

    def _set_date_range(self, start: str, end: str, days_back: int) -> None:
        print(f"[{self.CHANNEL_NAME}] 날짜 범위 설정: {start} ~ {end}", flush=True)

        # 전략 1: 기간 버튼 클릭
        if self._click_period_button(days_back):
            return

        # 전략 2: JS로 date input 강제 설정
        if self._fill_date_inputs_js(start, end):
            return

        print(f"[{self.CHANNEL_NAME}] 날짜 설정 실패 — 기본 조건으로 검색 진행", flush=True)

    def _click_period_button(self, days_back: int) -> bool:
        """기간 단축 버튼 클릭 (오늘/1주일/1개월/3개월)."""
        # days_back에 맞는 버튼 후보 (긴 것부터 단순한 것까지)
        mapping = {
            1:  ["오늘"],
            7:  ["1주일", "7일"],
            30: ["1개월", "30일"],
            90: ["3개월", "90일"],
        }
        candidates = mapping.get(days_back, [])
        if not candidates:
            for threshold in sorted(mapping.keys()):
                if days_back <= threshold:
                    candidates = mapping[threshold]
                    break
            if not candidates:
                candidates = ["3개월"]

        try:
            # Playwright locator로 텍스트 기반 탐색
            for label in candidates:
                try:
                    btn = self.page.locator(f"button:has-text('{label}'), a:has-text('{label}'), span:has-text('{label}')")
                    if btn.count() > 0:
                        first = btn.first
                        if first.is_visible():
                            first.click()
                            print(f"[{self.CHANNEL_NAME}] 기간 버튼 클릭: '{label}'", flush=True)
                            self.sleep(0.5, 1.0)
                            return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _fill_date_inputs_js(self, start: str, end: str) -> bool:
        """JS로 날짜 input 값 강제 설정."""
        try:
            result = self.page.evaluate(
                """([start, end]) => {
                    const inputs = Array.from(document.querySelectorAll('input'))
                        .filter(el => el.offsetParent !== null);

                    const dateInputs = inputs.filter(el => {
                        const ph = (el.placeholder || '').toLowerCase();
                        const nm = (el.name || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        return ph.includes('날') || ph.includes('date') || ph.includes('yy') ||
                               nm.includes('date') || nm.includes('from') || nm.includes('to') ||
                               cls.includes('date') || cls.includes('cal') || cls.includes('period');
                    });

                    if (dateInputs.length >= 2) {
                        function setVal(el, val) {
                            const nativeSet = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value').set;
                            nativeSet.call(el, val);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        setVal(dateInputs[0], start);
                        setVal(dateInputs[1], end);
                        return true;
                    }
                    return false;
                }""",
                [start, end],
            )
            if result:
                print(f"[{self.CHANNEL_NAME}] JS 날짜 입력 성공", flush=True)
                self.sleep(0.5, 1.0)
                return True
        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] JS 날짜 입력 오류: {e}", flush=True)
        return False

    # ── 검색 버튼 클릭 ────────────────────────────────

    def _click_search(self) -> None:
        """검색 버튼을 클릭한다."""
        # 전략 1: 정확한 텍스트 매칭
        for text in ["검색", "조회"]:
            try:
                btn = self.page.locator(f"button:has-text('{text}')")
                count = btn.count()
                for i in range(count):
                    try:
                        el = btn.nth(i)
                        # 공백/아이콘 제거 후 텍스트 매칭
                        raw_txt = el.inner_text() or ""
                        txt = re.sub(r"[^\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318Fa-zA-Z0-9]", "", raw_txt)
                        if text in txt and el.is_visible() and el.is_enabled():
                            el.click()
                            print(f"[{self.CHANNEL_NAME}] '{text}' 버튼 클릭 (txt='{raw_txt.strip()}')", flush=True)
                            return
                    except Exception:
                        continue
            except Exception:
                continue

        # 전략 2: type="submit" 버튼 시도
        try:
            submit_btn = self.page.locator("button[type='submit']")
            if submit_btn.count() > 0 and submit_btn.first.is_visible():
                submit_btn.first.click()
                print(f"[{self.CHANNEL_NAME}] submit 버튼 클릭", flush=True)
                return
        except Exception:
            pass

        print(f"[{self.CHANNEL_NAME}] 검색 버튼 없음 — 현재 결과 그대로 사용", flush=True)

    # ── 엑셀 다운로드 & 파싱 ─────────────────────────

    def _download_excel_and_parse(self, cutoff_date: datetime) -> list:
        """엑셀 다운로드 버튼 클릭 → 확인 팝업 처리 → 파일 파싱."""
        # 현재 페이지 상태 로그
        try:
            body_text = self.page.evaluate("() => document.body.innerText")
            print(
                f"[{self.CHANNEL_NAME}] 페이지 텍스트 샘플: {body_text[:200]}",
                flush=True,
            )
        except Exception:
            pass

        btn = self._find_excel_button()
        if not btn:
            print(f"[{self.CHANNEL_NAME}] 엑셀 다운로드 버튼을 찾지 못함", flush=True)
            return []

        tmp_path = os.path.join(tempfile.gettempdir(), f"ss_review_{int(time.time())}.xlsx")
        try:
            with self.page.expect_download(timeout=30000) as dl_info:
                self.page.evaluate("(el) => el.click()", btn)
                # 확인 팝업이 뜨면 "확인" 클릭
                self._confirm_download_popup()

            download = dl_info.value
            download.save_as(tmp_path)
            print(f"[{self.CHANNEL_NAME}] 엑셀 다운로드 완료: {tmp_path}", flush=True)

        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 다운로드 오류: {e}", flush=True)
            return []

        try:
            df = pd.read_excel(tmp_path, engine="openpyxl")
            print(
                f"[{self.CHANNEL_NAME}] 엑셀 파싱: {len(df)}행 / 컬럼: {list(df.columns)}",
                flush=True,
            )
            return self._parse_excel_df(df, cutoff_date)
        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 엑셀 파싱 오류: {e}", flush=True)
            return []
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def _find_excel_button(self) -> object:
        """엑셀 다운로드 버튼 element handle 반환."""
        # 스마트스토어 어드민의 실제 버튼 텍스트 후보
        search_texts = ["엑셀다운", "엑셀 다운", "엑셀다운로드", "엑셀 다운로드", "Excel", "다운로드"]

        # Playwright locator로 탐색
        for text in search_texts:
            try:
                loc = self.page.locator(f"button:has-text('{text}'), a:has-text('{text}')")
                if loc.count() > 0:
                    el = loc.first
                    if el.is_visible():
                        handle = el.element_handle()
                        if handle:
                            print(
                                f"[{self.CHANNEL_NAME}] 다운로드 버튼 발견: '{text}'",
                                flush=True,
                            )
                            return handle
            except Exception:
                continue

        # 추가 탐색: 모든 버튼/링크에서 "엑셀" 포함 텍스트 검색
        try:
            all_btns = self.page.locator("button, a[role='button'], a")
            count = min(all_btns.count(), 200)
            visible_texts = []
            for i in range(count):
                try:
                    el = all_btns.nth(i)
                    if not el.is_visible():
                        continue
                    txt = re.sub(r"\s+", "", el.inner_text() or "")
                    if txt:
                        visible_texts.append(txt)
                    if "엑셀" in txt or "excel" in txt.lower() or "download" in txt.lower():
                        handle = el.element_handle()
                        if handle:
                            print(
                                f"[{self.CHANNEL_NAME}] 다운로드 버튼 발견 (광범위): '{txt}'",
                                flush=True,
                            )
                            return handle
                except Exception:
                    continue
            # 버튼을 못 찾은 경우 실제 버튼 텍스트 목록 출력 (디버깅용)
            print(
                f"[{self.CHANNEL_NAME}] 화면의 버튼 텍스트 목록: {visible_texts[:30]}",
                flush=True,
            )
        except Exception as e:
            print(f"[{self.CHANNEL_NAME}] 버튼 탐색 오류: {e}", flush=True)

        return None

    def _confirm_download_popup(self) -> None:
        """다운로드 확인 팝업('리뷰 다운로드 및 활용에 유의해 주세요')의 확인 버튼 클릭."""
        self.sleep(0.5, 1.5)
        try:
            # "확인" 버튼 탐색
            confirm_btn = self.page.locator("button:has-text('확인')")
            if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                confirm_btn.first.click()
                print(f"[{self.CHANNEL_NAME}] 다운로드 확인 팝업 '확인' 클릭", flush=True)
                self.sleep(0.3, 0.7)
        except Exception:
            pass

    # ── 엑셀 컬럼 매핑 ───────────────────────────────

    _COL_MAP = {
        # 실제 다운로드 컬럼명 (2026-04 확인)
        "리뷰글번호": "review_id",          # 실제 컬럼명
        "리뷰상세내용": "content",           # 실제 컬럼명
        # 이전/다른 형태 호환
        "리뷰번호": "review_id",
        "리뷰내용": "content",
        "내용": "content",
        # 공통
        "채널상품번호": "channel_product_no",
        "상품번호": "channel_product_no",
        "상품명": "product_name",
        "옵션정보": "option_name",
        "옵션": "option_name",
        "구매자평점": "rating",
        "평점": "rating",
        "별점": "rating",
        "등록자": "customer_id",
        "작성자": "customer_id",
        "리뷰등록일": "review_date",
        "등록일": "review_date",
        "작성일": "review_date",
        "리뷰구분": "review_type",
        "답변상태": "reply_status_excel",
        "답글여부": "reply_status_excel",
    }

    def _normalize_col(self, name: str) -> str:
        return re.sub(r"[\s\(\)\[\]/·\-]", "", str(name))

    def _map_columns(self, df: pd.DataFrame) -> dict:
        result = {}
        for col in df.columns:
            norm = self._normalize_col(col)
            for key, field in self._COL_MAP.items():
                if norm == self._normalize_col(key):
                    if field not in result:
                        result[field] = col
                    break
        print(f"[{self.CHANNEL_NAME}] 컬럼 매핑 결과: {result}", flush=True)
        return result

    def _parse_excel_df(self, df: pd.DataFrame, cutoff_date: datetime) -> list:
        col_map = self._map_columns(df)
        reviews = []

        for _, row in df.iterrows():
            def get(field: str, default: str = "") -> str:
                col = col_map.get(field)
                if col is None:
                    return default
                val = row.get(col, default)
                if pd.isna(val):
                    return default
                return str(val).strip()

            content = get("content")
            if not content or len(content) < 5:
                continue
            if self._is_invalid_review_text(content):
                continue

            date_raw = get("review_date")
            review_date = self._normalize_date(date_raw)
            if not review_date:
                continue

            try:
                dt = datetime.strptime(review_date, "%Y-%m-%d")
                if dt < cutoff_date:
                    continue
            except Exception:
                continue

            rating_raw = get("rating", "5")
            try:
                m = re.search(r"\d", rating_raw)
                rating = int(m.group()) if m else 5
            except Exception:
                rating = 5

            review_id = get("review_id")
            customer_id = get("customer_id")
            if not review_id:
                review_id = f"{customer_id}_{review_date}_{len(reviews)}"

            reviews.append(
                {
                    "channel": self.CHANNEL_NAME,
                    "product_name": get("product_name", "메디셜"),
                    "option_name": get("option_name"),
                    "customer_id": customer_id,
                    "order_number": "",
                    "rating": rating,
                    "content": content,
                    "review_date": review_date,
                    "review_id_on_channel": review_id,
                }
            )

        return reviews

    # ── 유틸 ─────────────────────────────────────────

    def _normalize_date(self, date_str: str) -> str:
        date_str = (date_str or "").strip()

        # 2026.04.02 / 2026-04-02 / 2026/04/02
        m = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", date_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        # pandas Timestamp: 2026-04-02 00:00:00
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # 26.04.02
        m = re.search(r"(\d{2})[./-](\d{1,2})[./-](\d{1,2})", date_str)
        if m:
            return f"{2000 + int(m.group(1))}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        return ""

    def _is_masked_user_id(self, text: str) -> bool:
        return re.fullmatch(r"[A-Za-z0-9가-힣_]+[*]{2,}", (text or "").strip()) is not None

    INVALID_PATTERNS = [
        "리뷰이벤트",
        "AI 리뷰요약",
        "포토/동영상",
        "스토어PICK",
        "판매자 톡톡문의",
        "1:1 상담",
        "네이버 포인트",
        "상세정보",
        "Q&A",
    ]

    def _is_invalid_review_text(self, text: str) -> bool:
        text = (text or "").strip()
        if not text or len(text) < 5:
            return True
        if self._is_masked_user_id(text):
            return True
        for pattern in self.INVALID_PATTERNS:
            if pattern in text:
                return True
        return False
