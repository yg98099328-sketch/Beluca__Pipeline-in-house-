@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0.."

echo ============================================
echo 빌드/배포 산출물 삭제
echo (build\, release\, src\__pycache__)
echo ============================================

if exist "build" (
  rmdir /s /q "build"
  echo [삭제] build\
)
if exist "release" (
  rmdir /s /q "release"
  echo [삭제] release\
)
if exist "src\__pycache__" (
  rmdir /s /q "src\__pycache__"
  echo [삭제] src\__pycache__\
)

echo.
echo 완료. 소스는 src\ 에 그대로 있습니다.
echo 다시 빌드: 루트에서 build_exe.bat
pause
