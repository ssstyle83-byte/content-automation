@echo off
chcp 65001 > nul
echo ======================================
echo   원고 자동화 툴 설치를 시작합니다
echo ======================================
echo.

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org 에서 Python을 설치 후 다시 실행해주세요.
    echo.
    echo 설치 시 반드시 "Add Python to PATH" 에 체크하세요!
    pause
    exit /b
)

echo [완료] Python 확인:
python --version
echo.

:: 가상환경 생성
echo [진행] 가상환경 생성 중...
python -m venv venv
call venv\Scripts\activate

:: 패키지 설치
echo [진행] 필요한 패키지 설치 중... (시간이 걸릴 수 있어요)
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

:: Playwright Chromium 설치
echo [진행] 브라우저 설치 중... (시간이 걸릴 수 있어요)
playwright install chromium

echo.
echo ======================================
echo   설치가 완료되었습니다!
echo   run.bat 를 더블클릭하면 앱이 시작됩니다.
echo ======================================
pause