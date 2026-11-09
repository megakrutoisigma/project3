@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
for %%V in (3.14 3.13 3.12) do (
  py -%%V -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -%%V -m venv .venv
    if not errorlevel 1 goto dependencies
  )
)
echo Установите Python 3.12, 3.13 или 3.14 и повторите запуск.
pause
exit /b 1

:dependencies
".venv\Scripts\python.exe" -c "import pywebio, psutil" >nul 2>&1
if not errorlevel 1 goto launch
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Не удалось установить библиотеки. Проверьте подключение к интернету.
  pause
  exit /b 1
)

:launch
echo Открывается http://127.0.0.1:8080. Для остановки нажмите Ctrl+C.
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
