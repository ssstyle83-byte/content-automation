"""
경쟁사 분석 Streamlit 탭
기존 app.py에 추가하는 모듈
"""

import streamlit as st
import pandas as pd
import json
from datetime import datetime
from competitor_crawler import CompetitorCrawler, COMPETITORS, search_naver_shopping
from competitor_analyzer import full_analysis
from competitor_storage import (
    save_snapshot, load_latest_snapshot,
    detect_price_changes, get_price_history
)


def render_competitor_tab():
    """경쟁사 분석 탭 렌더링 - app.py에서 호출"""
    st.header("🔍 경쟁사 분석 자동화")

    # ── 사이드 설정
    with st.sidebar:
        st.subheader("⚙️ 경쟁사 설정")
        selected = st.multiselect(
            "분석할 경쟁사",
            list(COMPETITORS.keys()),
            default=list(COMPETITORS.keys())
        )
        use_playwright = st.checkbox("Playwright 상세 크롤링", value=False,
                                     help="더 정확하지만 시간이 걸립니다")
        headless = st.checkbox("브라우저 숨기기", value=True)

    # ── 탭 구성
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 가격 현황", "🏆 베스트 랭킹", "💬 리뷰 분석", "📈 가격 변화 추적"
    ])

    # ── 수집 버튼
    col1, col2 = st.columns([1, 3])
    with col1:
        run_btn = st.button("🚀 지금 수집", type="primary", use_container_width=True)
    with col2:
        st.caption(f"마지막 수집: {_get_last_collected()}")

    if run_btn:
        _run_collection(selected, use_playwright, headless)

    # ── 탭 1: 가격 현황
    with tab1:
        _render_price_tab(selected)

    # ── 탭 2: 베스트 랭킹
    with tab2:
        _render_ranking_tab(selected)

    # ── 탭 3: 리뷰 분석
    with tab3:
        _render_review_tab(selected)

    # ── 탭 4: 가격 변화
    with tab4:
        _render_price_history_tab(selected)


def _run_collection(selected: list, use_playwright: bool, headless: bool):
    """데이터 수집 실행"""
    progress = st.progress(0)
    status = st.empty()

    results = {}
    for i, name in enumerate(selected):
        status.info(f"⏳ {name} 수집 중...")
        progress.progress((i + 1) / len(selected))

        info = COMPETITORS[name]

        if use_playwright:
            crawler = CompetitorCrawler(headless=headless)
            data = crawler.crawl_one(name, info)
        else:
            # API만 사용 (빠름)
            products = search_naver_shopping(info["search_keyword"], display=20)
            data = {
                "name": name,
                "products": [],
                "best_products": products,
                "collected_at": datetime.now().isoformat()
            }

        save_snapshot(data, name)
        results[name] = data

    # 분석 실행
    status.info("🤖 Claude AI 분석 중...")
    st.session_state["competitor_results"] = results
    progress.progress(1.0)
    status.success("✅ 수집 완료!")


def _render_price_tab(selected: list):
    """가격 현황 탭"""
    st.subheader("경쟁사 가격 현황")

    all_products = []
    for name in selected:
        data = load_latest_snapshot(name)
        if not data:
            continue
        products = data.get("best_products", []) or data.get("products", [])
        for p in products:
            if p.get("price", 0) > 0:
                all_products.append({
                    "경쟁사": name,
                    "상품명": p.get("title", "")[:40],
                    "가격": p.get("price", 0),
                    "링크": p.get("link", "")
                })

    if all_products:
        df = pd.DataFrame(all_products)

        # 경쟁사별 평균가격 비교
        st.subheader("📊 경쟁사별 평균 가격")
        avg_prices = df.groupby("경쟁사")["가격"].agg(["mean", "min", "max"]).reset_index()
        avg_prices.columns = ["경쟁사", "평균가격", "최저가", "최고가"]
        avg_prices["평균가격"] = avg_prices["평균가격"].astype(int)
        st.bar_chart(avg_prices.set_index("경쟁사")["평균가격"])
        st.dataframe(avg_prices, use_container_width=True)

        # 전체 상품 목록
        st.subheader("📋 전체 상품 목록")
        st.dataframe(
            df[["경쟁사", "상품명", "가격"]].sort_values("가격"),
            use_container_width=True
        )
    else:
        st.info("데이터가 없습니다. '지금 수집' 버튼을 눌러주세요.")


def _render_ranking_tab(selected: list):
    """베스트 랭킹 탭"""
    st.subheader("🏆 경쟁사 베스트 상품")

    for name in selected:
        data = load_latest_snapshot(name)
        if not data:
            continue

        with st.expander(f"📦 {name}", expanded=True):
            products = data.get("best_products", []) or data.get("products", [])
            if products:
                rows = []
                for i, p in enumerate(products[:10], 1):
                    rows.append({
                        "순위": i,
                        "상품명": p.get("title", "")[:50],
                        "가격": f"{p.get('price', 0):,}원" if p.get('price') else "-",
                        "쇼핑몰": p.get("mall", "네이버")
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.caption("데이터 없음")


def _render_review_tab(selected: list):
    """리뷰 분석 탭"""
    st.subheader("💬 리뷰 키워드 분석")

    for name in selected:
        data = load_latest_snapshot(name)
        if not data:
            continue

        analysis = data.get("analysis", {})
        reviews = data.get("reviews_summary", [])

        with st.expander(f"🔍 {name} 리뷰 분석"):
            if analysis:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**✅ 강점**")
                    for s in analysis.get("strengths", []):
                        st.write(f"• {s}")
                with col2:
                    st.markdown("**❌ 약점**")
                    for w in analysis.get("weaknesses", []):
                        st.write(f"• {w}")

                st.markdown(f"**📝 요약:** {analysis.get('summary', '-')}")
                st.markdown(f"**😊 감성:** {analysis.get('sentiment', '-')}")

                keywords = analysis.get("keywords", [])
                if keywords:
                    st.markdown("**🏷️ 주요 키워드:** " + " | ".join([f"`{k}`" for k in keywords]))

            elif reviews:
                st.write("리뷰 샘플:")
                for r in reviews[:5]:
                    st.caption(f"• {r[:100]}")
            else:
                st.caption("리뷰 데이터 없음 (Playwright 수집 필요)")


def _render_price_history_tab(selected: list):
    """가격 변화 추적 탭"""
    st.subheader("📈 가격 변화 감지")

    all_changes = []
    for name in selected:
        changes = detect_price_changes(name)
        all_changes.extend(changes)

    if all_changes:
        st.warning(f"⚠️ 총 {len(all_changes)}건의 가격 변화 감지!")
        df = pd.DataFrame(all_changes)
        df["이전가격"] = df["previous_price"].apply(lambda x: f"{x:,}원")
        df["현재가격"] = df["current_price"].apply(lambda x: f"{x:,}원")
        df["변화율"] = df["change_pct"].apply(lambda x: f"{x:+.1f}%")
        st.dataframe(
            df[["competitor", "product", "이전가격", "현재가격", "direction", "변화율"]].rename(
                columns={"competitor": "경쟁사", "product": "상품명", "direction": "방향"}
            ),
            use_container_width=True
        )
    else:
        st.success("✅ 가격 변화 없음 (2회 이상 수집 후 비교 가능)")

    # 상품별 가격 히스토리
    st.subheader("상품별 가격 추이")
    comp_sel = st.selectbox("경쟁사 선택", selected)
    latest = load_latest_snapshot(comp_sel)
    if latest:
        products = latest.get("best_products", []) or latest.get("products", [])
        titles = [p.get("title", "")[:40] for p in products if p.get("title")]
        if titles:
            product_sel = st.selectbox("상품 선택", titles)
            history = get_price_history(comp_sel, product_sel)
            if len(history) > 1:
                df_hist = pd.DataFrame(history)
                st.line_chart(df_hist.set_index("date")["price"])
            else:
                st.info("2회 이상 수집 후 추이를 확인할 수 있습니다.")


def _get_last_collected() -> str:
    """마지막 수집 시간"""
    from pathlib import Path
    files = list(Path("competitor_data").glob("*.json")) if Path("competitor_data").exists() else []
    if not files:
        return "없음"
    latest = max(files, key=lambda f: f.stat().st_mtime)
    mtime = datetime.fromtimestamp(latest.stat().st_mtime)
    return mtime.strftime("%Y-%m-%d %H:%M")
