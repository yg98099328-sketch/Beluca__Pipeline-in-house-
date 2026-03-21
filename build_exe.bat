@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"
set "SRC=%ROOT%src"

echo ============================================
echo setup_pro EXE 빌드 시작
echo (소스: src\  /  출력: release\ )
echo ============================================

REM 버전 번호 자동 bump (VERSION.txt의 patch만 올림)
set "VER_FILE=%ROOT%VERSION.txt"
if not exist "%VER_FILE%" (
  echo 0.1.0>%VER_FILE%
)
set "VER="
for /f "usebackq delims=" %%v in ("%VER_FILE%") do set "VER=%%v"
if "%VER%"=="" set "VER=0.1.0"

for /f "tokens=1-3 delims=." %%a in ("%VER%") do (
  set "MAJ=%%a"
  set "MIN=%%b"
  set "PAT=%%c"
)
set /a "PAT=PAT+1" >nul 2>nul
set "NEW_VER=%MAJ%.%MIN%.%PAT%"
echo %NEW_VER%>"%VER_FILE%"

set "PY_CMD="

python -c "import sys; print(sys.executable)" >nul 2>nul
if not errorlevel 1 (
  set "PY_CMD=python"
)

if "%PY_CMD%"=="" (
  py -3 -c "import sys; print(sys.executable)" >nul 2>nul
  if not errorlevel 1 (
    set "PY_CMD=py -3"
  )
)

if "%PY_CMD%"=="" (
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PY_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"
  )
)
if "%PY_CMD%"=="" (
  if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
    set "PY_CMD=%LocalAppData%\Programs\Python\Python311\python.exe"
  )
)
if "%PY_CMD%"=="" (
  if exist "%ProgramFiles%\Python312\python.exe" (
    set "PY_CMD=%ProgramFiles%\Python312\python.exe"
  )
)
if "%PY_CMD%"=="" (
  if exist "%ProgramFiles%\Python311\python.exe" (
    set "PY_CMD=%ProgramFiles%\Python311\python.exe"
  )
)

if "%PY_CMD%"=="" (
  echo [안내] Python이 없어 자동 설치를 시도합니다...
  winget --version >nul 2>nul
  if errorlevel 1 (
    echo [오류] winget을 사용할 수 없습니다.
    echo 아래 링크에서 Python 3를 설치한 뒤 다시 실행하세요:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
  )

  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo [오류] Python 자동 설치 실패
    echo 수동 설치 후 다시 시도하세요: https://www.python.org/downloads/
    pause
    exit /b 1
  )

  echo [안내] 설치 직후 현재 CMD에는 PATH가 아직 반영되지 않는 경우가 많습니다.
  echo [안내] 레지스트리 Path + 일반 설치 경로에서 python.exe 를 다시 찾습니다...
  timeout /t 2 /nobreak >nul

  REM HKCU Path 를 이 세션에 합침 (설치기가 여기만 갱신하고 현재 창은 옛 PATH 인 경우)
  for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User')" 2^>nul`) do set "REG_USER_PATH=%%i"
  if defined REG_USER_PATH set "PATH=%REG_USER_PATH%;%PATH%"

  REM 시스템 Path 도 합침 (일부 설치)
  for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine')" 2^>nul`) do set "REG_MACHINE_PATH=%%i"
  if defined REG_MACHINE_PATH set "PATH=%PATH%;%REG_MACHINE_PATH%"

  set "PATH=%PATH%;%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts"

  python -c "import sys; print(sys.executable)" >nul 2>nul
  if not errorlevel 1 (
    set "PY_CMD=python"
  )

  if "%PY_CMD%"=="" (
    py -3 -c "import sys; print(sys.executable)" >nul 2>nul
    if not errorlevel 1 (
      set "PY_CMD=py -3"
    )
  )

  if "%PY_CMD%"=="" (
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
      set "PY_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"
    )
  )
  if "%PY_CMD%"=="" (
    if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
      set "PY_CMD=%LocalAppData%\Programs\Python\Python311\python.exe"
    )
  )
  REM winget/python.org 설치 폴더명이 Python313 등일 수 있음 → 하위 폴더 검색
  if "%PY_CMD%"=="" (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
      if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
    )
  )
  if "%PY_CMD%"=="" (
    if exist "%ProgramFiles%\Python312\python.exe" (
      set "PY_CMD=%ProgramFiles%\Python312\python.exe"
    )
  )
  if "%PY_CMD%"=="" (
    if exist "%ProgramFiles%\Python311\python.exe" (
      set "PY_CMD=%ProgramFiles%\Python311\python.exe"
    )
  )

  if "%PY_CMD%"=="" (
    echo [오류] Python 설치 후에도 실행기 인식 실패
    echo 다음을 확인하세요:
    echo   1^) 이 배치 파일을 닫고 새 CMD에서 build_exe.bat 다시 실행
    echo   2^) 또는 Python 설치 시 "Add python.exe to PATH" 옵션
    echo   3^) 수동: python.org 에서 설치 후 PC 재시작
    pause
    exit /b 1
  )
)

echo [정보] 사용 Python 명령: %PY_CMD%

if not exist "%SRC%\setup_pro_manager.py" (
  echo [오류] %SRC%\setup_pro_manager.py 가 없습니다.
  pause
  exit /b 1
)

call %PY_CMD% -m pip --version >nul 2>nul
if errorlevel 1 (
  echo [오류] pip를 사용할 수 없습니다. Python 설치를 확인하세요.
  pause
  exit /b 1
)

call %PY_CMD% -m pip install --upgrade pip
if errorlevel 1 (
  echo [오류] pip 업데이트 실패
  pause
  exit /b 1
)

call %PY_CMD% -m pip install pyinstaller customtkinter
if errorlevel 1 (
  echo [오류] pyinstaller / customtkinter 설치 실패
  pause
  exit /b 1
)

set "BUILD_SUFFIX=%~1"
if "%BUILD_SUFFIX%"=="" (
  set "BUILD_SUFFIX="
) else (
  if /I "%BUILD_SUFFIX%"=="next" (
    set "BUILD_SUFFIX=_next"
  )
)

set "OUT_NAME=setup_pro_manager%BUILD_SUFFIX%"

call %PY_CMD% -m PyInstaller --noconfirm --onefile --windowed ^
  "%SRC%\setup_pro_manager.py" ^
  --name %OUT_NAME% ^
  --distpath "%ROOT%release" ^
  --workpath "%ROOT%build" ^
  --add-data "%SRC%\setup_pro_common.py;." ^
  --add-data "%SRC%\nuke_setup_pro.py;." ^
  --add-data "%SRC%\menu.py;." ^
  --add-data "%SRC%\shot_node_template.nk;." ^
  --add-data "%ROOT%scripts\install_to_nuke.bat;." ^
  --add-data "%ROOT%VERSION.txt;." ^
  --collect-data customtkinter ^
  --hidden-import customtkinter
if errorlevel 1 (
  echo [오류] EXE 빌드 명령 실행 실패
  pause
  exit /b 1
)

if exist "%ROOT%release\%OUT_NAME%.exe" (
  echo.
  echo [완료] EXE 생성됨: release\%OUT_NAME%.exe
  echo.
  echo [배포 패키지] release\ 폴더에 Nuke 연동 파일 복사 중...
  copy /Y "%SRC%\setup_pro_common.py" "%ROOT%release\setup_pro_common.py" >nul
  copy /Y "%SRC%\nuke_setup_pro.py" "%ROOT%release\nuke_setup_pro.py" >nul
  copy /Y "%SRC%\menu.py" "%ROOT%release\menu.py" >nul
  copy /Y "%ROOT%scripts\install_to_nuke.bat" "%ROOT%release\install_to_nuke.bat" >nul
  copy /Y "%ROOT%VERSION.txt" "%ROOT%release\VERSION.txt" >nul
  (
    echo @echo off
    echo cd /d "%%~dp0"
    echo if exist "setup_pro_manager.exe" ^(
    echo   start "" "setup_pro_manager.exe"
    echo ^) else if exist "setup_pro_manager_next.exe" ^(
    echo   start "" "setup_pro_manager_next.exe"
    echo ^) else ^(
    echo   echo EXE 파일을 찾을 수 없습니다.
    echo   pause
    echo ^)
  ) > "%ROOT%release\실행.bat"
  if exist "%ROOT%docs\배포_사용법.txt" (
    copy /Y "%ROOT%docs\배포_사용법.txt" "%ROOT%release\README_사용법.txt" >nul
  ) else (
    (
      echo setup_pro 사용 방법
      echo.
      echo 1. 이 폴더를 zip으로 묶어 전달하거나 폴더째 복사
      echo 2. setup_pro_manager.exe 또는 실행.bat 실행
      echo 3. Nuke 연동: install_to_nuke.bat 실행 후 Nuke 재시작
    ) > "%ROOT%release\README_사용법.txt"
  )
  echo.
  echo [배포] release\ 폴더 전체를 압축하거나 공유하세요.
) else (
  echo.
  echo [오류] EXE 생성 실패. 메시지를 확인하세요.
)

if /I "%NOPAUSE%"=="1" (
  exit /b 0
) else (
  pause
)
