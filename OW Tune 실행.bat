@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo 처음 실행: 가상환경을 만들고 필요한 패키지를 설치합니다...
  python -m venv .venv || goto :err
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
)
start "" ".venv\Scripts\pythonw.exe" -m owtune
exit /b

:err
echo 설치에 실패했습니다. Python 3.11 이상이 설치돼 있는지 확인하세요.
pause
