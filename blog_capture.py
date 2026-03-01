from playwright.sync_api import sync_playwright
import os
import re
import time
from datetime import datetime

CAPTURES_DIR = "captures"

def capture_blog(url, product_folder, base_dir=CAPTURES_DIR):
    """네이버 블로그 본문 전체 캡처"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1200, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # 제목 추출
            title = page.title()
            title = re.sub(r'\s*::\s*네이버 블로그.*', '', title).strip()
            title = re.sub(r'[\\/:*?"<>|]', '', title).strip()
            if not title:
                title = "capture"

            # 파일명: YYMMDD_제목.png
            date_str = datetime.now().strftime("%y%m%d")
            filename = f"{date_str}_{title}.png"

            # 저장 폴더
            save_dir = os.path.join(base_dir, product_folder)
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, filename)

            captured = False

            # iframe 방식 시도 (네이버 블로그 주요 구조)
            try:
                frame = page.frame("mainFrame")
                if frame:
                    time.sleep(2)

                    # 스크롤해서 전체 콘텐츠 로딩
                    frame.evaluate("""
                        async () => {
                            await new Promise(resolve => {
                                let totalHeight = 0;
                                const distance = 300;
                                const timer = setInterval(() => {
                                    window.scrollBy(0, distance);
                                    totalHeight += distance;
                                    if (totalHeight >= document.body.scrollHeight) {
                                        clearInterval(timer);
                                        window.scrollTo(0, 0);
                                        resolve();
                                    }
                                }, 100);
                            });
                        }
                    """)
                    time.sleep(2)

                    # 본문 전체 높이 가져오기
                    for sel in [".se-main-container", "#postViewArea", ".post-view", "body"]:
                        try:
                            el = frame.locator(sel).first
                            if el.count() > 0:
                                # 요소 전체 높이로 뷰포트 확장
                                height = frame.evaluate(
                                    f"document.querySelector('{sel}').scrollHeight"
                                )
                                page.set_viewport_size({"width": 1200, "height": min(height + 100, 30000)})
                                time.sleep(1)
                                el.screenshot(path=save_path)
                                captured = True
                                break
                        except Exception:
                            continue
            except Exception:
                pass

            # 직접 셀렉터 방식
            if not captured:
                # 스크롤해서 전체 콘텐츠 로딩
                page.evaluate("""
                    async () => {
                        await new Promise(resolve => {
                            let totalHeight = 0;
                            const distance = 300;
                            const timer = setInterval(() => {
                                window.scrollBy(0, distance);
                                totalHeight += distance;
                                if (totalHeight >= document.body.scrollHeight) {
                                    clearInterval(timer);
                                    window.scrollTo(0, 0);
                                    resolve();
                                }
                            }, 100);
                        });
                    }
                """)
                time.sleep(2)

                for sel in [".se-main-container", "#postViewArea", ".post-view"]:
                    try:
                        el = page.locator(sel).first
                        if el.count() > 0:
                            height = page.evaluate(
                                f"document.querySelector('{sel}').scrollHeight"
                            )
                            page.set_viewport_size({"width": 1200, "height": min(height + 100, 30000)})
                            time.sleep(1)
                            el.screenshot(path=save_path)
                            captured = True
                            break
                    except Exception:
                        continue

            # 전체 페이지 캡처 (fallback)
            if not captured:
                page.screenshot(path=save_path, full_page=True)

            return {
                "success": True,
                "path": save_path,
                "title": title,
                "filename": filename
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            browser.close()