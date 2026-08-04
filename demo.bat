@echo off
REM Spusti ukazku bez API klice. Data jsou SMYSLENA.
cd /d "%~dp0"
where python >nul 2>nul || (echo Chybi Python 3.10+. & pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
echo Instaluji zavislosti...
pip install -q -e ".[dev]"
recon discover --mock --from fixtures/demo_events.json
recon recon --mock --fixture fixtures/sample_event.html --attendees data/attendees_example.csv
recon watch >nul
echo.
echo ===============================================
echo  Hotovo. Otevri v prohlizeci:
echo    %cd%\demo\index.html
echo.
echo  POZOR: vsechna data jsou smyslena (rok 2099).
echo ===============================================
pause
