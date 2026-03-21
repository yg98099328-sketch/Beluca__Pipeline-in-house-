@echo off
chcp 65001 >nul
setlocal EnableExtensions

REM 배포 폴더(release)에서 실행: 같은 폴더의 .py 복사
REM 개발 시: scripts\ 에서 실행하면 ..\src\ 사용
set "HERE=%~dp0"
if exist "%HERE%setup_pro_common.py" (
  set "PY_SRC=%HERE%"
) else if exist "%HERE%..\src\setup_pro_common.py" (
  set "PY_SRC=%HERE%..\src\"
) else (
  echo [오류] setup_pro_common.py 를 찾을 수 없습니다.
  echo 배포 폴더 또는 프로젝트 scripts 폴더에서 실행하세요.
  pause
  exit /b 1
)

set "NUKE_DIR=%USERPROFILE%\.nuke"

echo ============================================
echo setup_pro Nuke 연동 설치
echo ============================================

if not exist "%NUKE_DIR%" (
  mkdir "%NUKE_DIR%"
)

copy /Y "%PY_SRC%setup_pro_common.py" "%NUKE_DIR%\setup_pro_common.py" >nul
copy /Y "%PY_SRC%nuke_setup_pro.py" "%NUKE_DIR%\nuke_setup_pro.py" >nul
copy /Y "%PY_SRC%menu.py" "%NUKE_DIR%\menu.py" >nul

echo.
echo [완료] 설치 경로:
echo %NUKE_DIR%
echo.
echo Nuke를 재시작하면 상단에 setup_pro 메뉴가 나타납니다.
pause
