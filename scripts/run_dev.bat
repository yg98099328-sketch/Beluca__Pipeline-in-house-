@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo [개발 실행] Python으로 GUI 실행 (EXE 빌드 없이)
echo.

python -c "import sys; raise SystemExit(0)" >nul 2>nul
if not errorlevel 1 (
  python "src\setup_pro_manager.py"
  goto :end
)

py -3 "src\setup_pro_manager.py" 2>nul
if not errorlevel 1 goto :end

echo [오류] python / py 명령을 찾을 수 없습니다. Python 3를 설치하세요.
pause
exit /b 1

:end
if errorlevel 1 pause
