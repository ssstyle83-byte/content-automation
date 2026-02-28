import streamlit as st
import anthropic
import json
import os
import re
from datetime import datetime
from dotenv import load_dotenv

from datetime import time as dtime


load_dotenv()

# ── 기본 설정 ──────────────────────────────────────
PROMPTS_FILE = "prompts.json"
OUTPUTS_DIR  = "outputs"
SCHEDULE_FILE = "schedule_config.json"
os.makedirs(OUTPUTS_DIR, exist_ok=True)

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

def get_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
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
tab1, tab2, tab3, tab4 = st.tabs(["📝 원고 생성", "📋 프롬프트 관리", "⏰ 예약 실행", "⚙️ 설정"])


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

        # 결과 출력
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
    st.info("예약 실행은 **scheduler.py** 를 별도로 실행해야 동작합니다. (아래 안내 참고)")

    prompts = load_prompts()
    col_a, col_b = st.columns([1, 1])

    with col_a:
        st.subheader("예약 설정")
        sch_prompt = st.selectbox("프롬프트", list(prompts.keys()) if prompts else ["없음"])
        sch_keywords = st.text_area("키워드 목록", height=150, placeholder="키워드1\n키워드2\n키워드3")
     
        sch_time = st.time_input("실행 시간", value=dtime(9, 0))
        sch_hour   = sch_time.hour
        sch_minute = sch_time.minute

        sch_model  = st.selectbox("모델 ", [
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
# TAB 4 : 설정
# ══════════════════════════════════════════════════
with tab4:
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
    st.subheader(f"저장된 원고 ({OUTPUTS_DIR}/)")
    if os.path.exists(OUTPUTS_DIR):
        files = sorted(os.listdir(OUTPUTS_DIR), reverse=True)
        if files:
            st.write(f"총 {len(files)}개")
            for fname in files[:30]:
                st.text(f"📄 {fname}")
        else:
            st.info("아직 저장된 원고가 없습니다.")
