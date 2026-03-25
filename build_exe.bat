@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"
set "SRC=%ROOT%src"

echo ============================================
echo   BELUCA Pipeline Engine - BPE build
echo   Source: src\   Output: release\
echo ============================================

REM --- version bump ---
set "VER_FILE=%ROOT%VERSION.txt"
if not exist "%VER_FILE%" (
  echo 0.1.0>"%VER_FILE%"
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
echo [version] BPE v%NEW_VER%

REM --- find Python ---
set "PY_CMD="

python -c "import sys; print(sys.executable)" >nul 2>nul
if not errorlevel 1 set "PY_CMD=python"

if "%PY_CMD%"=="" (
  py -3 -c "import sys; print(sys.executable)" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=py -3"
)

if "%PY_CMD%"=="" (
  for %%V in (313 312 311 310) do (
    if "%PY_CMD%"=="" (
      if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
        set "PY_CMD=%LocalAppData%\Programs\Python\Python%%V\python.exe"
      )
    )
    if "%PY_CMD%"=="" (
      if exist "%ProgramFiles%\Python%%V\python.exe" (
        set "PY_CMD=%ProgramFiles%\Python%%V\python.exe"
      )
    )
  )
)

if "%PY_CMD%"=="" (
  echo [error] Python not found. Install from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo [info] Python: %PY_CMD%

if not exist "%SRC%\setup_pro_manager.py" (
  echo [error] Missing %SRC%\setup_pro_manager.py
  pause
  exit /b 1
)

call "%PY_CMD%" -m pip --version >nul 2>nul
if errorlevel 1 (
  echo [error] pip not available
  pause
  exit /b 1
)

call "%PY_CMD%" -m pip install --upgrade pip --quiet
call "%PY_CMD%" -m pip install pyinstaller customtkinter reportlab shotgun_api3 tkinterdnd2 --quiet
if errorlevel 1 (
  echo [error] pip install failed
  pause
  exit /b 1
)

REM --- output exe name ---
REM 기본 빌드는 BPE_build_staging.exe 로 먼저 만든 뒤 BPE.exe 로 옮깁니다.
REM (PyInstaller 가 기존 BPE.exe 를 지우려다 "액세스가 거부" 나는 것을 피함 — 실행 중 EXE 잠금)
set "BUILD_SUFFIX=%~1"
set "NEXT_STAGING=BPE_next_staging"
set "STAGING_EXE=BPE_build_staging"
if /I "%BUILD_SUFFIX%"=="next" (
  set "OUT_NAME=%NEXT_STAGING%"
  set "PYI_NAME=%NEXT_STAGING%"
) else (
  set "OUT_NAME=BPE"
  set "PYI_NAME=%STAGING_EXE%"
)

REM PyInstaller (one line; use CRLF in this .bat file)
call "%PY_CMD%" -m PyInstaller --noconfirm --clean --onefile --windowed "%SRC%\setup_pro_manager.py" --name %PYI_NAME% --distpath "%ROOT%release" --workpath "%ROOT%build" --add-data "%SRC%\setup_pro_common.py;." --add-data "%SRC%\shotgrid_client.py;." --add-data "%SRC%\nuke_setup_pro.py;." --add-data "%SRC%\menu.py;." --add-data "%SRC%\shot_node_template.nk;." --add-data "%ROOT%scripts\install_to_nuke.bat;." --add-data "%ROOT%VERSION.txt;." --collect-data customtkinter --collect-all tkinterdnd2 --hidden-import customtkinter --hidden-import shotgun_api3 --hidden-import shotgun_api3.lib.httplib2 --hidden-import shotgun_api3.lib.sgtimezone --hidden-import certifi --hidden-import six --hidden-import urllib3 --hidden-import tkinterdnd2
if errorlevel 1 (
  echo [error] PyInstaller failed
  pause
  exit /b 1
)

REM --- default: staging -> BPE.exe (BPE.exe 가 잠겨 있으면 버전만 복사본 유지) ---
if /I not "%BUILD_SUFFIX%"=="next" (
  if not exist "%ROOT%release\%STAGING_EXE%.exe" (
    echo [error] %STAGING_EXE%.exe not found after build
    if /I not "%NOPAUSE%"=="1" pause
    exit /b 1
  )
  copy /Y "%ROOT%release\%STAGING_EXE%.exe" "%ROOT%release\BPE v%NEW_VER%.exe" >nul
  echo [file] BPE v%NEW_VER%.exe ^(버전 복사본^)
  del /F /Q "%ROOT%release\BPE.exe" >nul 2>&1
  if exist "%ROOT%release\BPE.exe" (
    echo [warn] BPE.exe 를 덮어쓸 수 없습니다 ^(실행 중이거나 잠금^). 새 빌드: release\BPE v%NEW_VER%.exe
    del /F /Q "%ROOT%release\%STAGING_EXE%.exe" >nul 2>&1
  ) else (
    move /Y "%ROOT%release\%STAGING_EXE%.exe" "%ROOT%release\BPE.exe" >nul
    if errorlevel 1 (
      echo [error] BPE.exe 로 이름 바꾸기 실패
      if /I not "%NOPAUSE%"=="1" pause
      exit /b 1
    )
  )
)

REM --- next: rename staging to BPE_next.exe ---
if /I "%BUILD_SUFFIX%"=="next" (
  if exist "%ROOT%release\%NEXT_STAGING%.exe" (
    del /F /Q "%ROOT%release\BPE_next.exe" >nul 2>&1
    if exist "%ROOT%release\BPE_next.exe" (
      echo.
      echo [warn] BPE_next.exe is locked. Use release\%NEXT_STAGING%.exe
    ) else (
      move /Y "%ROOT%release\%NEXT_STAGING%.exe" "%ROOT%release\BPE_next.exe" >nul
      if exist "%ROOT%release\BPE_next.exe" (
        echo [info] BPE_next.exe updated
      ) else (
        echo [error] rename to BPE_next.exe failed
        if /I not "%NOPAUSE%"=="1" pause
        exit /b 1
      )
    )
  ) else (
    echo [error] %NEXT_STAGING%.exe not found
    if /I not "%NOPAUSE%"=="1" pause
    exit /b 1
  )
)

REM --- copy release files ---
set "HAS_REL_EXE=0"
if /I "%BUILD_SUFFIX%"=="next" (
  if exist "%ROOT%release\BPE_next.exe" set "HAS_REL_EXE=1"
  if exist "%ROOT%release\%NEXT_STAGING%.exe" set "HAS_REL_EXE=1"
) else (
  if exist "%ROOT%release\BPE.exe" set "HAS_REL_EXE=1"
  if exist "%ROOT%release\BPE v%NEW_VER%.exe" set "HAS_REL_EXE=1"
)
if "%HAS_REL_EXE%"=="1" (
  echo.
  if /I "%BUILD_SUFFIX%"=="next" (
    if exist "%ROOT%release\BPE_next.exe" (
      echo [done] release\BPE_next.exe
    ) else (
      echo [done] release\%NEXT_STAGING%.exe
    )
  ) else (
    echo [done] release\%OUT_NAME%.exe
  )
  echo.
  echo [release] copying helper files...

  copy /Y "%SRC%\setup_pro_common.py" "%ROOT%release\setup_pro_common.py" >nul
  copy /Y "%SRC%\shotgrid_client.py" "%ROOT%release\shotgrid_client.py" >nul
  copy /Y "%SRC%\nuke_setup_pro.py" "%ROOT%release\nuke_setup_pro.py" >nul
  copy /Y "%SRC%\menu.py" "%ROOT%release\menu.py" >nul
  copy /Y "%ROOT%scripts\install_to_nuke.bat" "%ROOT%release\install_to_nuke.bat" >nul
  copy /Y "%ROOT%scripts\install_setup_pro_menu.ps1" "%ROOT%release\install_setup_pro_menu.ps1" >nul
  copy /Y "%ROOT%VERSION.txt" "%ROOT%release\VERSION.txt" >nul
  if exist "%ROOT%shotgrid_studio.json.example" copy /Y "%ROOT%shotgrid_studio.json.example" "%ROOT%release\shotgrid_studio.json.example" >nul

  echo @echo off> "%ROOT%release\run_bpe.bat"
  echo cd /d "%%~dp0">> "%ROOT%release\run_bpe.bat"
  echo set "FOUND=">> "%ROOT%release\run_bpe.bat"
  echo for %%%%f in ("BPE v*.exe") do if not defined FOUND set "FOUND=%%%%f">> "%ROOT%release\run_bpe.bat"
  echo if defined FOUND start "" "%%FOUND%%">> "%ROOT%release\run_bpe.bat"
  echo if not defined FOUND if exist "BPE.exe" start "" "BPE.exe">> "%ROOT%release\run_bpe.bat"

  echo BPE v%NEW_VER%> "%ROOT%release\README.txt"
  echo Run BPE.exe or run_bpe.bat>> "%ROOT%release\README.txt"
  echo Nuke: run install_to_nuke.bat once.>> "%ROOT%release\README.txt"

  echo.
  echo [release] Zip the release\ folder to distribute.
) else (
  echo.
  echo [error] EXE was not created.
)

if /I "%NOPAUSE%"=="1" (
  exit /b 0
) else (
  pause
)
