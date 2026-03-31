import streamlit as st
import anthropic
import json
import os
import re
from datetime import datetime, time as dtime
from dotenv import load_dotenv
from blog_capture import capture_blog
from competitor_ui import render_competitor_tab
import db
import analyzer
import reply_generator
import auto_poster
from crawlers import CRAWLERS

load_dotenv()

# ── 기본 설정 ──────────────────────────────────────
PROMPTS_FILE  = "prompts.json"
PRODUCTS_FILE = "products.json"
OUTPUTS_DIR   = "outputs"
SCHEDULE_FILE = "schedule_config.json"
CAPTURES_DIR  = "captures"
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(CAPTURES_DIR, exist_ok=True)

st.set_page_config(page_title="원고 출력 자동화", page_icon="✍️", layout="wide")
st.title("✍️ 원고 출력 자동화")

# ── 유틸 함수 ──────────────────────────────────────
def load_prompts():
    if os.path.exists(PROMPTS_FILE):
        try:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except (json.JSONDecodeError, Exception):
            return {}
    return {}

def save_prompts(prompts):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        try:
            with open(PRODUCTS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def get_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            pass
    if not api_key:
        st.error("API 키가 없습니다. [설정] 탭에서 입력해주세요.")
        return None
    return anthropic.Anthropic(api_key=api_key)

def count_keyword(text, keyword):
    return len(re.findall(re.escape(keyword), text, re.IGNORECASE))

def generate_content(prompt_template, keyword, model):
    client = get_client()
    if not client:
        return None
    prompt = prompt_template.replace("{keyword}", keyword)
    msg = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

def verify_content(content, keyword):
    client = get_client()
    if not client:
        return None
    prompt = f"""아래 원고를 검토하고 반드시 JSON만 출력하세요.

원고:
{content}

키워드: {keyword}

{{
  "score": 0~100 사이 숫자,
  "factual_accuracy": "사실 정확도 한 줄 평가",
  "keyword_natural": "키워드 자연스러움 한 줄 평가",
  "issues": ["문제점1", "문제점2"],
  "suggestions": ["개선점1", "개선점2"]
}}"""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        match = re.search(r'\{.*\}', msg.content[0].text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None

def save_output(keyword, content):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUTS_DIR, f"{timestamp}_{keyword}.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    return filename

# ── session state 초기화 ───────────────────────────
if "results" not in st.session_state:
    st.session_state.results = []

# ── 탭 구성 ───────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    "📝 원고 생성",
    "📋 프롬프트 관리",
    "⏰ 예약 실행",
    "📸 블로그 캡처",
    "🔍 경쟁사 분석",
    "⚙️ 설정",
    "📊 CS/리뷰 대시보드",
    "🔄 데이터 수집",
    "💬 답변 관리",
    "🏷️ 분석 리포트",
])


# ══════════════════════════════════════════════════
# TAB 1 : 원고 생성
# ══════════════════════════════════════════════════
with tab1:
    prompts = load_prompts()

    if not prompts:
        st.warning("등록된 프롬프트가 없어요. [프롬프트 관리] 탭에서 먼저 추가해주세요.")
    else:
        col_left, col_right = st.columns([1, 1])

        with col_left:
            selected = st.selectbox("프롬프트 선택", list(prompts.keys()))
            keywords_input = st.text_area(
                "키워드 입력 (줄바꿈으로 여러 개 가능)",
                height=140,
                placeholder="혈압관리\n당뇨식단\n체중감량"
            )
            model = st.selectbox("모델", [
                "claude-sonnet-4-5-20250929",
                "claude-haiku-4-5-20251001"
            ])
            do_verify = st.checkbox("신뢰도 검증 포함", value=True)
            run_btn = st.button("🚀 원고 생성", type="primary", use_container_width=True)

        with col_right:
            if selected:
                st.caption("선택된 프롬프트")
                st.text_area("", value=prompts[selected], height=220, disabled=True)

        if run_btn:
            if not keywords_input.strip():
                st.error("키워드를 입력해주세요.")
            else:
                keywords = [k.strip() for k in keywords_input.strip().splitlines() if k.strip()]
                progress = st.progress(0)

                for i, kw in enumerate(keywords):
                    with st.spinner(f"[{i+1}/{len(keywords)}] '{kw}' 생성 중..."):
                        content = generate_content(prompts[selected], kw, model)

                    if content:
                        filename = save_output(kw, content)
                        result = {
                            "keyword": kw,
                            "content": content,
                            "chars": len(content),
                            "kw_count": count_keyword(content, kw),
                            "file": filename,
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "verification": None
                        }
                        if do_verify:
                            with st.spinner(f"'{kw}' 신뢰도 검증 중..."):
                                result["verification"] = verify_content(content, kw)

                        st.session_state.results.insert(0, result)

                    progress.progress((i + 1) / len(keywords))

                st.success(f"✅ {len(keywords)}개 원고 생성 완료!")

        if st.session_state.results:
            st.divider()
            for i, r in enumerate(st.session_state.results):
                label = f"📄 {r['keyword']}  |  {r['chars']:,}자  |  키워드 {r['kw_count']}회  |  {r['time']}"
                with st.expander(label, expanded=(i == 0)):
                    m1, m2, m3 = st.columns(3)
                    m1.metric("글자 수", f"{r['chars']:,}자")
                    m2.metric("키워드 반복", f"{r['kw_count']}회")
                    m3.metric("생성 시간", r['time'])

                    v = r.get("verification")
                    if v:
                        score = v.get("score", "-")
                        color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
                        st.info(
                            f"{color} **신뢰도 {score}점**  "
                            f"|  사실정확도: {v.get('factual_accuracy','')}  "
                            f"|  키워드: {v.get('keyword_natural','')}"
                        )
                        if v.get("issues"):
                            st.warning("⚠️ 문제점: " + "  /  ".join(v["issues"]))
                        if v.get("suggestions"):
                            st.success("💡 개선점: " + "  /  ".join(v["suggestions"]))

                    st.text_area("원고", value=r["content"], height=300, key=f"r_{i}")
                    st.caption(f"저장 위치: {r['file']}")


# ══════════════════════════════════════════════════
# TAB 2 : 프롬프트 관리
# ══════════════════════════════════════════════════
with tab2:
    prompts = load_prompts()
    col_a, col_b = st.columns([1, 1])

    with col_a:
        st.subheader("새 프롬프트 추가")
        new_name = st.text_input("프롬프트 이름", placeholder="예: 건강식품_블로그")
        new_body = st.text_area(
            "프롬프트 내용  (키워드 위치는 {keyword} 로 표시)",
            height=260,
            placeholder="{keyword}에 대한 블로그 원고를 작성해주세요.\n\n요구사항:\n- 글자 수: 2000자 이상\n- 어조: 친근하고 전문적\n- 소제목 3개 이상 포함"
        )
        if st.button("➕ 추가", type="primary", use_container_width=True):
            if new_name and new_body:
                prompts[new_name] = new_body
                save_prompts(prompts)
                st.success(f"'{new_name}' 추가 완료!")
                st.rerun()
            else:
                st.error("이름과 내용을 모두 입력해주세요.")

    with col_b:
        st.subheader(f"등록된 프롬프트 ({len(prompts)}개)")
        if not prompts:
            st.info("아직 프롬프트가 없습니다.")
        else:
            for name, body in list(prompts.items()):
                with st.expander(f"📋 {name}"):
                    edited = st.text_area("내용", value=body, height=200, key=f"e_{name}")
                    c1, c2 = st.columns(2)
                    if c1.button("💾 저장", key=f"s_{name}", use_container_width=True):
                        prompts[name] = edited
                        save_prompts(prompts)
                        st.success("저장 완료")
                        st.rerun()
                    if c2.button("🗑️ 삭제", key=f"d_{name}", use_container_width=True):
                        del prompts[name]
                        save_prompts(prompts)
                        st.rerun()


# ══════════════════════════════════════════════════
# TAB 3 : 예약 실행
# ══════════════════════════════════════════════════
with tab3:
    st.info("예약 실행은 **scheduler.py** 를 별도로 실행해야 동작합니다.")

    prompts = load_prompts()
    col_a, col_b = st.columns([1, 1])

    with col_a:
        st.subheader("예약 설정")
        sch_prompt   = st.selectbox("프롬프트", list(prompts.keys()) if prompts else ["없음"])
        sch_keywords = st.text_area("키워드 목록", height=150, placeholder="키워드1\n키워드2\n키워드3")
        sch_time     = st.time_input("실행 시간", value=dtime(9, 0))
        sch_hour     = sch_time.hour
        sch_minute   = sch_time.minute
        sch_model    = st.selectbox("모델 ", [
            "claude-sonnet-4-5-20250929",
            "claude-haiku-4-5-20251001"
        ])

        c1, c2 = st.columns(2)
        if c1.button("⏰ 예약 등록", type="primary", use_container_width=True):
            if sch_keywords.strip() and sch_prompt != "없음":
                cfg = {
                    "prompt_name": sch_prompt,
                    "keywords": sch_keywords.strip(),
                    "hour": sch_hour,
                    "minute": sch_minute,
                    "model": sch_model,
                    "active": True
                }
                with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                st.success(f"매일 {sch_hour:02d}:{sch_minute:02d}에 자동 실행 등록!")
            else:
                st.error("프롬프트와 키워드를 입력해주세요.")

        if c2.button("❌ 예약 취소", use_container_width=True):
            if os.path.exists(SCHEDULE_FILE):
                os.remove(SCHEDULE_FILE)
                st.success("예약 취소됨")
            st.rerun()

    with col_b:
        st.subheader("현재 예약 상태")
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            st.success("🟢 예약 활성화")
            st.write(f"**프롬프트:** {cfg['prompt_name']}")
            st.write(f"**실행 시간:** {cfg['hour']:02d}:{cfg['minute']:02d}")
            st.write(f"**모델:** {cfg['model']}")
            kws = cfg['keywords'].splitlines()
            st.write(f"**키워드 수:** {len(kws)}개")
            st.text_area("키워드 목록", value=cfg['keywords'], height=150, disabled=True)
        else:
            st.warning("🔴 등록된 예약 없음")

        st.divider()
        st.caption("scheduler.py 실행 방법")
        st.code("python scheduler.py", language="bash")


# ══════════════════════════════════════════════════
# TAB 4 : 블로그 캡처
# ══════════════════════════════════════════════════
with tab4:
    st.info("⚠️ 이 기능은 로컬 실행 전용입니다. Streamlit Cloud에서는 동작하지 않아요.")

    col_a, col_b = st.columns([1, 1])

    with col_a:
        st.subheader("제품 목록 관리")
        products = load_products()

        new_product = st.text_input("새 제품 추가", placeholder="예: 혈압관리")
        if st.button("➕ 제품 추가"):
            if new_product and new_product not in products:
                products.append(new_product)
                save_products(products)
                st.success(f"'{new_product}' 추가됨")
                st.rerun()
            elif new_product in products:
                st.warning("이미 등록된 제품입니다.")

        if products:
            st.write("**등록된 제품:**")
            for p in products:
                col_p, col_d = st.columns([3, 1])
                col_p.write(f"📁 {p}")
                if col_d.button("삭제", key=f"del_p_{p}"):
                    products.remove(p)
                    save_products(products)
                    st.rerun()
        else:
            st.info("등록된 제품이 없습니다.")

    with col_b:
        st.subheader("블로그 캡처")
        products = load_products()

        if not products:
            st.warning("먼저 왼쪽에서 제품을 등록해주세요.")
        else:
            selected_product = st.selectbox("저장할 제품 폴더", products)
            urls_input = st.text_area(
                "블로그 링크 입력 (줄바꿈으로 여러 개)",
                height=180,
                placeholder="https://blog.naver.com/xxx/111\nhttps://blog.naver.com/xxx/222"
            )

            if st.button("📸 캡처 시작", type="primary", use_container_width=True):
                if not urls_input.strip():
                    st.error("링크를 입력해주세요.")
                else:
                    urls = [u.strip() for u in urls_input.strip().splitlines() if u.strip()]
                    progress = st.progress(0)

                    for i, url in enumerate(urls):
                        with st.spinner(f"[{i+1}/{len(urls)}] 캡처 중..."):
                            result = capture_blog(url, selected_product)

                        if result["success"]:
                            st.success(f"✅ {result['filename']} 저장 완료")
                            st.image(result["path"], caption=result["title"], use_container_width=True)
                        else:
                            st.error(f"❌ 실패: {result['error']}")

                        progress.progress((i + 1) / len(urls))

                    st.balloons()


# ══════════════════════════════════════════════════
# TAB 5 : 경쟁사 분석
# ══════════════════════════════════════════════════
with tab5:
    render_competitor_tab()


# ══════════════════════════════════════════════════
# TAB 6 : 설정
# ══════════════════════════════════════════════════
with tab6:
    st.subheader("Claude API 키")

    current = os.getenv("ANTHROPIC_API_KEY", "")
    if current:
        masked = current[:8] + "••••••••" + current[-4:]
        st.success(f"현재 키: `{masked}`")
    else:
        st.warning("API 키가 설정되지 않았습니다.")

    new_key = st.text_input("새 API 키", type="password", placeholder="sk-ant-...")
    if st.button("💾 저장"):
        if new_key:
            with open(".env", "w") as f:
                f.write(f"ANTHROPIC_API_KEY={new_key}\n")
            os.environ["ANTHROPIC_API_KEY"] = new_key
            st.success("저장 완료! 앱을 재시작하면 반영됩니다.")
        else:
            st.error("키를 입력해주세요.")

    st.divider()
    st.subheader("네이버 API 키 (경쟁사 분석용)")
    naver_id = os.getenv("NAVER_CLIENT_ID", "")
    if naver_id:
        st.success(f"네이버 Client ID: `{naver_id[:4]}••••`")
    else:
        st.warning("네이버 API 키 없음 (경쟁사 분석 시 Playwright만 사용됩니다)")

    st.caption("네이버 API 발급: https://developers.naver.com → 검색 API 신청")
    n1 = st.text_input("NAVER_CLIENT_ID", placeholder="네이버 Client ID")
    n2 = st.text_input("NAVER_CLIENT_SECRET", type="password", placeholder="네이버 Client Secret")
    if st.button("💾 네이버 API 저장"):
        if n1 and n2:
            existing = ""
            if os.path.exists(".env"):
                with open(".env", "r") as f:
                    existing = f.read()
            with open(".env", "w") as f:
                lines = [l for l in existing.splitlines()
                         if not l.startswith("NAVER_CLIENT_ID") and not l.startswith("NAVER_CLIENT_SECRET")]
                lines += [f"NAVER_CLIENT_ID={n1}", f"NAVER_CLIENT_SECRET={n2}"]
                f.write("\n".join(lines) + "\n")
            os.environ["NAVER_CLIENT_ID"] = n1
            os.environ["NAVER_CLIENT_SECRET"] = n2
            st.success("네이버 API 키 저장 완료!")
        else:
            st.error("ID와 Secret을 모두 입력해주세요.")

    st.divider()
    st.subheader(f"저장된 원고 ({OUTPUTS_DIR}/)")
    if os.path.exists(OUTPUTS_DIR):
        files = sorted(os.listdir(OUTPUTS_DIR), reverse=True)
        if files:
            st.write(f"총 {len(files)}개")
            for fname in files[:30]:
                st.text(f"📄 {fname}")
        else:
            st.info("아직 저장된 원고가 없습니다.")


# ══════════════════════════════════════════════════
# TAB 7 : CS/리뷰 대시보드
# ══════════════════════════════════════════════════
with tab7:
    st.subheader("📊 CS/리뷰 현황 대시보드")

    # 미해결 알림 배너
    alerts = db.get_unresolved_alerts()
    if alerts:
        for a in [x for x in alerts if x["level"] == "critical"][:3]:
            col_al, col_btn = st.columns([8, 1])
            col_al.error(f"🚨 **[긴급]** {a['message']}")
            if col_btn.button("해결", key=f"resolve_{a['id']}"):
                db.resolve_alert(a["id"]); st.rerun()
        for a in [x for x in alerts if x["level"] == "warning"][:3]:
            col_al, col_btn = st.columns([8, 1])
            col_al.warning(f"⚠️ {a['message']}")
            if col_btn.button("해결", key=f"resolve_{a['id']}"):
                db.resolve_alert(a["id"]); st.rerun()

    # 채널별 통계 카드
    stats = db.get_review_stats()
    if stats:
        st.markdown("#### 채널별 리뷰 현황")
        cols = st.columns(min(len(stats), 3))
        for i, (channel, s) in enumerate(stats.items()):
            with cols[i % 3]:
                avg_r = s.get("avg_rating") or 0
                neg_rate = round(100 * s.get("neg_count", 0) / max(s.get("total", 1), 1), 1)
                st.metric(label=channel, value=f"총 {s.get('total', 0)}건",
                          delta=f"미답변 {s.get('pending_count', 0)}건")
                st.caption(f"평균 평점 {avg_r:.1f}점 | 부정 {neg_rate}% | 위험 {s.get('risk_count', 0)}건")
    else:
        st.info("수집된 리뷰 데이터가 없습니다. [데이터 수집] 탭에서 수집을 시작하세요.")

    st.divider()

    # 상품별 클레임율 테이블
    st.markdown("#### 상품별 클레임율 (부정 리뷰 비율)")
    claim_data = db.get_claim_rates()
    if claim_data:
        try:
            import pandas as pd
            df = pd.DataFrame(claim_data)
            df.columns = ["상품명", "옵션", "채널", "총 리뷰", "부정 리뷰", "클레임율(%)"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        except ImportError:
            for r in claim_data:
                st.write(f"**{r['product_name']}** ({r['channel']}) — 클레임율 {r['claim_rate']}%")
    else:
        st.info("클레임율 데이터가 없습니다.")

    st.divider()
    col_r, col_c = st.columns(2)
    with col_r:
        st.markdown("#### 미답변 리뷰")
        st.metric("자동 등록 대기", f"{len(db.get_reviews(status='pending', limit=500))}건")
        st.metric("검토 필요 (위험)", f"{len(db.get_reviews(status='review_needed', limit=500))}건",
                  delta_color="inverse")
    with col_c:
        st.markdown("#### 미답변 CS")
        st.metric("자동 등록 대기", f"{len(db.get_cs_items(status='pending', limit=500))}건")
        st.metric("검토 필요 (위험)", f"{len(db.get_cs_items(status='review_needed', limit=500))}건",
                  delta_color="inverse")


# ══════════════════════════════════════════════════
# TAB 8 : 데이터 수집
# ══════════════════════════════════════════════════
with tab8:
    st.subheader("🔄 채널 데이터 수집")
    st.info("선택한 채널의 리뷰와 CS 문의를 자동으로 수집합니다. .env 파일에 각 채널 계정 정보를 입력해야 합니다.")

    # ── 로그인 세션 관리 ──────────────────────────────
    with st.expander("🔑 로그인 세션 관리 (수동 로그인 필요 채널)", expanded=True):
        st.markdown(
            "일부 채널(네이버 스마트스토어 등)은 보안 정책으로 자동 로그인이 차단됩니다. "
            "**수동 로그인** 버튼을 누르면 브라우저 창이 열리고, 직접 로그인(2차 인증 포함)하면 "
            "세션이 저장되어 이후 자동 수집 시 재사용됩니다."
        )
        sess_cols = st.columns(len(CRAWLERS))
        for i, (ch_name, crawler_cls) in enumerate(CRAWLERS.items()):
            with sess_cols[i]:
                needs_login = bool(crawler_cls.LOGIN_URL)
                if not needs_login:
                    st.markdown(f"**{ch_name}**  \n🟢 로그인 불필요")
                    st.caption("공개 페이지 수집")
                else:
                    has_session = crawler_cls.session_exists()
                    status_icon = "🟢" if has_session else "🔴"
                    st.markdown(f"**{ch_name}**  \n{status_icon} {'세션 있음' if has_session else '세션 없음'}")
                    if st.button(f"수동 로그인", key=f"login_{ch_name}", use_container_width=True):
                        with st.spinner(f"{ch_name} 브라우저를 열고 있습니다. 로그인 완료 후 자동으로 저장됩니다..."):
                            try:
                                success = crawler_cls.manual_login_and_save()
                                if success:
                                    st.success(f"✅ {ch_name} 세션 저장 완료!")
                                else:
                                    st.error(f"❌ {ch_name} 로그인 시간 초과 또는 실패")
                            except Exception as e:
                                st.error(f"로그인 오류: {e}")
                    if has_session:
                        if st.button(f"세션 삭제", key=f"del_sess_{ch_name}", use_container_width=True,
                                     type="secondary"):
                            crawler_cls.delete_session()
                            st.info(f"{ch_name} 세션이 삭제되었습니다.")
                            st.rerun()
    st.divider()

    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown("#### 수집 설정")
        selected_channels = st.multiselect("수집할 채널 선택", list(CRAWLERS.keys()),
                                           default=["스마트스토어"])
        period = st.selectbox("수집 기간", ["오늘 (1일)", "최근 7일", "최근 30일", "최근 90일"])
        days_back = {"오늘 (1일)": 1, "최근 7일": 7, "최근 30일": 30, "최근 90일": 90}[period]
        do_analyze = st.checkbox("수집 후 자동 분석 (감정/이슈 태깅)", value=True)
        do_generate_reply = st.checkbox("분석 후 자동 답변 생성", value=True)
        do_auto_post = st.checkbox("답변 자동 등록 (위험 항목 제외)", value=False)
        headless_mode = st.checkbox("백그라운드 실행 (창 숨김)", value=True)
        run_btn = st.button("🚀 수집 시작", type="primary", use_container_width=True)

    with col_right:
        st.markdown("#### 수집 결과")

    if run_btn:
        if not selected_channels:
            st.error("채널을 하나 이상 선택해주세요.")
        else:
            progress = st.progress(0)
            status_text = st.empty()
            for ch_idx, channel in enumerate(selected_channels):
                status_text.text(f"[{ch_idx+1}/{len(selected_channels)}] {channel} 수집 중...")
                try:
                    crawler = CRAWLERS[channel](headless=headless_mode)
                    result = crawler.run_collect(days_back=days_back)
                    if result.get("error"):
                        st.error(f"[{channel}] {result['error']}")
                    else:
                        new_reviews = sum(1 for rv in result.get("reviews", []) if db.upsert_review(rv))
                        new_cs = sum(1 for cs in result.get("cs", []) if db.upsert_cs(cs))
                        st.success(f"✅ [{channel}] 리뷰 {new_reviews}건, CS {new_cs}건 수집 완료")

                        if do_analyze and new_reviews > 0:
                            status_text.text(f"[{channel}] 감정 분석 중...")
                            with db.get_conn() as conn:
                                ids = [r["id"] for r in conn.execute(
                                    "SELECT id FROM reviews WHERE channel=? AND sentiment='neutral' ORDER BY id DESC LIMIT 100",
                                    (channel,)).fetchall()]
                            if ids:
                                a_r = analyzer.analyze_batch(ids)
                                st.info(f"  분석 완료: {a_r['processed']}건")

                        if do_generate_reply:
                            status_text.text(f"[{channel}] 답변 생성 중...")
                            with db.get_conn() as conn:
                                ids = [r["id"] for r in conn.execute(
                                    "SELECT id FROM reviews WHERE channel=? AND reply_draft IS NULL ORDER BY id DESC LIMIT 50",
                                    (channel,)).fetchall()]
                            if ids:
                                r_r = reply_generator.generate_replies_batch(ids)
                                st.info(f"  답변 생성: {r_r['generated']}건")

                        if do_auto_post:
                            status_text.text(f"[{channel}] 답변 자동 등록 중...")
                            p_r = auto_poster.post_review_replies(channel=channel)
                            st.info(f"  자동 등록: {p_r['posted']}건 성공 / {p_r['failed']}건 실패")
                except Exception as e:
                    st.error(f"[{channel}] 수집 오류: {e}")
                progress.progress((ch_idx + 1) / len(selected_channels))
            status_text.text("수집 완료!")
            if st.button("📊 대시보드에서 결과 보기", type="primary"):
                st.rerun()


# ══════════════════════════════════════════════════
# TAB 9 : 답변 관리
# ══════════════════════════════════════════════════
with tab9:
    st.subheader("💬 답변 관리")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filter_channel = st.selectbox("채널 필터", ["전체"] + list(CRAWLERS.keys()), key="f_ch")
    with col_f2:
        filter_status = st.selectbox(
            "상태 필터",
            ["pending (미답변)", "review_needed (검토필요)", "posted (완료)", "전체"],
            key="f_st"
        )
    with col_f3:
        filter_type = st.selectbox("유형", ["리뷰", "CS 문의"], key="f_type")

    status_map = {"pending (미답변)": "pending", "review_needed (검토필요)": "review_needed",
                  "posted (완료)": "posted", "전체": None}
    ch_filter = None if filter_channel == "전체" else filter_channel
    st_filter = status_map[filter_status]

    col_btn1, _ = st.columns([1, 3])
    with col_btn1:
        if st.button("⚡ 전체 자동 등록", type="primary",
                     help="pending 상태 + 위험 아님 항목을 일괄 등록"):
            with st.spinner("자동 등록 중..."):
                result = (auto_poster.post_review_replies(channel=ch_filter)
                          if filter_type == "리뷰"
                          else auto_poster.post_cs_replies(channel=ch_filter))
            st.success(f"등록 완료: {result['posted']}건 성공 / {result['failed']}건 실패")
            st.rerun()

    st.divider()
    items = (db.get_reviews(channel=ch_filter, status=st_filter, limit=50)
             if filter_type == "리뷰"
             else db.get_cs_items(channel=ch_filter, status=st_filter, limit=50))

    if not items:
        st.info("해당 조건의 데이터가 없습니다.")
    else:
        st.caption(f"총 {len(items)}건")
        for item in items:
            is_risk = bool(item.get("is_risk"))
            status = item.get("reply_status", "")
            try:
                tags = json.loads(item.get("issue_tags") or "[]")
            except Exception:
                tags = []
            rating_str = f"⭐{item['rating']}" if item.get("rating") else ""
            risk_flag = "🚨 위험" if is_risk else ""
            status_icon = {"pending": "🔵", "review_needed": "🔴", "posted": "✅"}.get(status, "⚪")
            label = (f"{status_icon} [{item.get('channel','')}] "
                     f"{item.get('product_name','') or item.get('title','')} "
                     f"{rating_str} {risk_flag}")

            with st.expander(label, expanded=False):
                col_info, col_reply = st.columns([1, 1])
                with col_info:
                    if filter_type == "리뷰":
                        st.text_area("리뷰 내용", value=item.get("content",""), height=120,
                                     disabled=True, key=f"content_{item['id']}")
                    else:
                        st.markdown(f"**{item.get('title','')}**")
                        st.text_area("내용", value=item.get("content",""), height=100,
                                     disabled=True, key=f"cs_content_{item['id']}")
                    date_val = item.get("review_date") or item.get("inquiry_date","")
                    st.caption(f"날짜: {date_val}")
                    if item.get("customer_id"):
                        st.caption(f"고객 아이디: {item['customer_id']}")
                    if tags:
                        st.caption(f"이슈: {', '.join(tags)}")
                    if is_risk and item.get("risk_reason"):
                        st.warning(f"⚠️ 위험 사유: {item['risk_reason']}")

                with col_reply:
                    current_draft = item.get("reply_draft") or ""
                    if not current_draft:
                        if st.button("✨ 답변 생성", key=f"gen_{item['id']}"):
                            with st.spinner("생성 중..."):
                                draft = (reply_generator.generate_reply(item)
                                         if filter_type == "리뷰"
                                         else reply_generator.generate_cs_reply(item))
                                new_status = "review_needed" if is_risk else "pending"
                                if filter_type == "리뷰":
                                    db.update_review_reply(item["id"], draft, new_status)
                                else:
                                    db.update_cs_reply(item["id"], draft, new_status)
                            st.rerun()
                    else:
                        edited = st.text_area("답변 초안", value=current_draft, height=140,
                                              key=f"draft_{item['id']}")
                        col_save, col_post = st.columns(2)
                        if col_save.button("💾 저장", key=f"save_{item['id']}"):
                            if filter_type == "리뷰":
                                db.update_review_reply(item["id"], edited)
                            else:
                                db.update_cs_reply(item["id"], edited)
                            st.success("저장됨"); st.rerun()
                        if col_post.button(
                            "✅ 완료" if status == "posted" else "📤 등록",
                            key=f"post_{item['id']}", disabled=(status == "posted")
                        ):
                            with st.spinner("등록 중..."):
                                ok = (auto_poster.post_single_review_reply(item["id"])
                                      if filter_type == "리뷰"
                                      else auto_poster.post_single_cs_reply(item["id"]))
                            (st.success("등록 완료!") if ok else st.error("등록 실패"))
                            if ok: st.rerun()


# ══════════════════════════════════════════════════
# TAB 10 : 분석 리포트
# ══════════════════════════════════════════════════
with tab10:
    st.subheader("🏷️ 분석 리포트")
    col_period, _ = st.columns([1, 2])
    with col_period:
        report_period = st.selectbox("기간", ["최근 7일", "최근 30일", "최근 90일"], key="rp")
    period_days = {"최근 7일": 7, "최근 30일": 30, "최근 90일": 90}[report_period]

    try:
        import pandas as pd

        st.markdown("#### 이슈 유형 TOP 10")
        issue_summary = analyzer.get_issue_summary(days_back=period_days)
        if issue_summary:
            df_issue = pd.DataFrame(list(issue_summary.items())[:10], columns=["이슈 유형", "건수"])
            st.bar_chart(df_issue.set_index("이슈 유형"))
        else:
            st.info("이슈 데이터가 없습니다.")

        st.divider()
        st.markdown("#### 감정 분포 트렌드 (일별)")
        trend = analyzer.get_sentiment_trend(days_back=period_days)
        if trend:
            df_trend = pd.DataFrame(trend).rename(columns={
                "review_date": "날짜", "positive": "긍정", "negative": "부정", "neutral": "중립"
            })
            st.line_chart(df_trend.set_index("날짜")[["긍정", "부정", "중립"]])
        else:
            st.info("트렌드 데이터가 없습니다.")

        st.divider()
        st.markdown("#### 채널별 통계 요약")
        stats = db.get_review_stats()
        if stats:
            rows = [{
                "채널": ch,
                "총 리뷰": s.get("total", 0),
                "평균 평점": round(s.get("avg_rating") or 0, 1),
                "부정 리뷰": s.get("neg_count", 0),
                "부정 비율(%)": round(100 * s.get("neg_count", 0) / max(s.get("total", 1), 1), 1),
                "미답변": s.get("pending_count", 0),
                "위험": s.get("risk_count", 0),
            } for ch, s in stats.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("통계 데이터가 없습니다.")

        st.divider()
        st.markdown("#### 상품별 클레임율 (3건 이상)")
        claim_data = db.get_claim_rates()
        if claim_data:
            df_claim = pd.DataFrame(claim_data)
            df_claim.columns = ["상품명", "옵션", "채널", "총 리뷰", "부정 리뷰", "클레임율(%)"]
            st.dataframe(df_claim, use_container_width=True, hide_index=True)
            csv = df_claim.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("📥 CSV 다운로드", data=csv.encode("utf-8-sig"),
                               file_name=f"claim_rate_{datetime.now().strftime('%Y%m%d')}.csv",
                               mime="text/csv")
        else:
            st.info("클레임율 데이터가 없습니다.")
    except ImportError:
        st.error("pandas 패키지가 필요합니다. `pip install pandas`를 실행해주세요.")
