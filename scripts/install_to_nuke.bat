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

REM menu.py 는 기존 TD/파이프라인 내용을 덮어쓰지 않고 hook 만 추가합니다.
set "PS1=%HERE%install_setup_pro_menu.ps1"
if exist "%PS1%" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -NukeHome "%NUKE_DIR%" -TemplateMenu "%PY_SRC%menu.py"
  if errorlevel 1 (
    echo [경고] menu.py 자동 병합에 실패했습니다. PowerShell 실행이 막혀 있을 수 있습니다.
    echo        문서의 "menu.py 수동 연동" 절을 참고하세요.
  )
) else (
  echo [경고] install_setup_pro_menu.ps1 을 찾을 수 없어 menu.py 를 갱신하지 못했습니다.
  echo        배포 폴더 전체를 복사했는지 확인하세요.
)

echo.
echo [완료] 설치 경로:
echo %NUKE_DIR%
echo.
echo Nuke를 재시작하면 상단에 setup_pro 메뉴가 나타납니다.
echo  * 기존 menu.py 가 있으면 내용은 유지되고 hook 만 추가됩니다.
pause
