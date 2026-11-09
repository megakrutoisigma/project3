@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите start.bat для настройки окружения, затем остановите сервер.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Не удалось установить зависимости сборки.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --name PC-Info-Web --collect-data pywebio --add-data "assets;assets" app.py
if errorlevel 1 (
  echo Ошибка сборки. Проверьте Python и зависимости.
  pause
  exit /b 1
)
echo Готово: dist\PC-Info-Web.exe
pause
