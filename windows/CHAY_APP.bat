@echo off
chcp 65001 >nul
setlocal
title Phien Dich Cuoc Hop - Anh / Viet

rem ============================================================
rem  Nhap dup vao file nay la chay duoc.
rem  Lan dau se tu cai dat (mat vai phut), cac lan sau mo thang GUI.
rem ============================================================

cd /d "%~dp0.."

set "VENV_PY=.venv\Scripts\python.exe"

rem ---- Neu da cai roi thi mo thang GUI ----
if exist "%VENV_PY%" goto :launch

rem ---- Lan dau: tim Python roi chay cai dat ----
echo.
echo ============================================================
echo   LAN DAU CHAY - DANG CAI DAT
echo   Viec nay mat vai phut, chi lam mot lan duy nhat.
echo ============================================================
echo.

set "SYS_PY="
where py >nul 2>&1 && set "SYS_PY=py -3"
if not defined SYS_PY (
    where python >nul 2>&1 && set "SYS_PY=python"
)

if not defined SYS_PY (
    echo.
    echo  !! KHONG TIM THAY PYTHON TREN MAY NAY.
    echo.
    echo  Hay cai Python 3.11 hoac 3.12 ^(ban 64-bit^) tai:
    echo      https://www.python.org/downloads/
    echo.
    echo  QUAN TRONG: luc cai nho TICH vao o "Add Python to PATH".
    echo  Cai xong thi chay lai file nay.
    echo.
    pause
    exit /b 1
)

%SYS_PY% setup_env.py --skip-test
if errorlevel 1 (
    echo.
    echo  !! CAI DAT KHONG THANH CONG. Xem thong bao loi o tren.
    echo.
    pause
    exit /b 1
)

:launch
rem ---- Kiem tra nhanh: thieu giong doc thi cai bu ----
if not exist "models\piper\vi_VN-vais1000-medium.onnx" (
    echo Thieu giong doc, dang tai bu...
    "%VENV_PY%" setup_env.py --skip-test
)

echo.
echo Dang mo ung dung... ^(lan dau tai model co the mat vai phut^)
echo.
"%VENV_PY%" main.py

if errorlevel 1 (
    echo.
    echo  !! Ung dung thoat voi loi. Chay lenh nay de xem chan doan:
    echo       %VENV_PY% main.py --test
    echo.
    pause
)

endlocal
