"""
경쟁사 데이터 저장 및 히스토리 관리
가격 변화 감지 + 알림
"""

import json
import os
import smtplib
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

DATA_DIR = Path("competitor_data")
DATA_DIR.mkdir(exist_ok=True)


def save_snapshot(data: dict, competitor_name: str):
    """크롤링 결과 스냅샷 저장"""
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = DATA_DIR / f"{competitor_name}_{date_str}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[저장] {filename}")


def load_latest_snapshot(competitor_name: str) -> dict:
    """가장 최근 스냅샷 로드"""
    files = sorted(DATA_DIR.glob(f"{competitor_name}_*.json"))
    if not files:
        return {}
    with open(files[-1], "r", encoding="utf-8") as f:
        return json.load(f)


def load_previous_snapshot(competitor_name: str) -> dict:
    """이전 스냅샷 로드 (비교용)"""
    files = sorted(DATA_DIR.glob(f"{competitor_name}_*.json"))
    if len(files) < 2:
        return {}
    with open(files[-2], "r", encoding="utf-8") as f:
        return json.load(f)


def detect_price_changes(competitor_name: str) -> list:
    """가격 변화 감지"""
    current = load_latest_snapshot(competitor_name)
    previous = load_previous_snapshot(competitor_name)

    if not current or not previous:
        return []

    changes = []
    current_products = {p.get("title"): p for p in current.get("products", []) + current.get("best_products", [])}
    previous_products = {p.get("title"): p for p in previous.get("products", []) + previous.get("best_products", [])}

    for title, curr in current_products.items():
        if title in previous_products:
            curr_price = curr.get("price", 0)
            prev_price = previous_products[title].get("price", 0)
            if curr_price and prev_price and curr_price != prev_price:
                diff = curr_price - prev_price
                diff_pct = round(diff / prev_price * 100, 1)
                changes.append({
                    "competitor": competitor_name,
                    "product": title,
                    "previous_price": prev_price,
                    "current_price": curr_price,
                    "change": diff,
                    "change_pct": diff_pct,
                    "direction": "인상 📈" if diff > 0 else "인하 📉"
                })

    return changes


def send_alert_email(changes: list, new_products: list, smtp_config: dict):
    """가격 변화 이메일 알림"""
    if not changes and not new_products:
        return

    if not smtp_config.get("email"):
        print("[알림] 이메일 설정 없음, 콘솔 출력으로 대체")
        _print_alert(changes, new_products)
        return

    subject = f"[경쟁사 알림] 가격변화 {len(changes)}건 / 신상품 {len(new_products)}건"

    body_lines = ["<h2>📊 경쟁사 가격 변화 알림</h2>"]

    if changes:
        body_lines.append("<h3>💰 가격 변화</h3><table border='1' cellpadding='5'>")
        body_lines.append("<tr><th>경쟁사</th><th>상품명</th><th>이전가격</th><th>현재가격</th><th>변화</th></tr>")
        for c in changes:
            body_lines.append(
                f"<tr><td>{c['competitor']}</td><td>{c['product'][:30]}</td>"
                f"<td>{c['previous_price']:,}원</td><td>{c['current_price']:,}원</td>"
                f"<td>{c['direction']} {abs(c['change_pct'])}%</td></tr>"
            )
        body_lines.append("</table>")

    if new_products:
        body_lines.append("<h3>🆕 신상품 감지</h3><ul>")
        for p in new_products:
            body_lines.append(f"<li>{p.get('competitor')} - {p.get('title')} ({p.get('price', 0):,}원)</li>")
        body_lines.append("</ul>")

    body_lines.append(f"<p><small>수집 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}</small></p>")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_config["email"]
        msg["To"] = smtp_config["email"]
        msg.attach(MIMEText("\n".join(body_lines), "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_config["email"], smtp_config["password"])
            server.send_message(msg)
        print(f"[알림] 이메일 발송 완료: {subject}")
    except Exception as e:
        print(f"[알림] 이메일 실패: {e}")
        _print_alert(changes, new_products)


def _print_alert(changes: list, new_products: list):
    """콘솔 출력 알림"""
    if changes:
        print("\n⚠️  가격 변화 감지!")
        for c in changes:
            print(f"  {c['competitor']} - {c['product'][:30]}: {c['previous_price']:,}원 → {c['current_price']:,}원 ({c['direction']})")
    if new_products:
        print("\n🆕 신상품 감지!")
        for p in new_products:
            print(f"  {p.get('competitor')} - {p.get('title')}")


def get_price_history(competitor_name: str, product_title: str) -> list:
    """특정 상품의 가격 히스토리 조회"""
    files = sorted(DATA_DIR.glob(f"{competitor_name}_*.json"))
    history = []

    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            data = json.load(file)
        products = data.get("products", []) + data.get("best_products", [])
        for p in products:
            if product_title in p.get("title", ""):
                history.append({
                    "date": f.stem.split("_")[1],
                    "price": p.get("price", 0)
                })
                break

    return history
