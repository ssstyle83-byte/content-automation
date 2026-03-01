#!/bin/bash

echo "======================================"
echo "  원고 자동화 툴 설치를 시작합니다"
echo "======================================"
echo ""

# Python 설치 확인
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3가 설치되어 있지 않습니다."
    echo "   https://www.python.org 에서 Python을 설치 후 다시 실행해주세요."
    read -p "엔터를 누르면 종료됩니다..."
    exit 1
fi

echo "✅ Python 확인 완료: $(python3 --version)"
echo ""

# 가상환경 생성
echo "📦 가상환경 생성 중..."
python3 -m venv venv
source venv/bin/activate

# 패키지 설치
echo "📦 필요한 패키지 설치 중... (시간이 걸릴 수 있어요)"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# Playwright Chromium 설치
echo "🌐 브라우저 설치 중... (시간이 걸릴 수 있어요)"
playwright install chromium

echo ""
echo "======================================"
echo "  ✅ 설치가 완료되었습니다!"
echo "  run.sh 를 더블클릭하면 앱이 시작됩니다."
echo "======================================"
read -p "엔터를 누르면 종료됩니다..."