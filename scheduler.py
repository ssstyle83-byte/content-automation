import json
import os
import re
import time
import anthropic
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

PROMPTS_FILE  = "prompts.json"
SCHEDULE_FILE = "schedule_config.json"
OUTPUTS_DIR   = "outputs"
os.makedirs(OUTPUTS_DIR, exist_ok=True)

def load_prompts():
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def generate(prompt_template, keyword, model, api_key):
    client = anthropic.Anthropic(api_key=api_key)
    prompt = prompt_template.replace("{keyword}", keyword)
    msg = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

def run_scheduled():
    if not os.path.exists(SCHEDULE_FILE):
        return

    with open(SCHEDULE_FILE, encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("active"):
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] API 키가 없습니다.")
        return

    prompts = load_prompts()
    prompt_name = cfg["prompt_name"]
    if prompt_name not in prompts:
        print(f"[ERROR] 프롬프트 '{prompt_name}' 를 찾을 수 없습니다.")
        return

    keywords = [k.strip() for k in cfg["keywords"].splitlines() if k.strip()]
    model    = cfg.get("model", "claude-sonnet-4-5-20250929")

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 예약 실행 시작 — {len(keywords)}개 키워드")

    for kw in keywords:
        try:
            print(f"  생성 중: {kw}")
            content = generate(prompts[prompt_name], kw, model, api_key)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(OUTPUTS_DIR, f"{timestamp}_{kw}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✅ 저장: {path}")
        except Exception as e:
            print(f"  ❌ 실패 ({kw}): {e}")

    print("예약 실행 완료\n")

def main():
    print("스케줄러 시작. 종료하려면 Ctrl+C")
    while True:
        now = datetime.now()

        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            if (cfg.get("active") and
                    now.hour == cfg["hour"] and
                    now.minute == cfg["minute"] and
                    now.second < 30):
                run_scheduled()
                time.sleep(60)  # 같은 분에 중복 실행 방지

        time.sleep(20)  # 20초마다 시간 체크

if __name__ == "__main__":
    main()
