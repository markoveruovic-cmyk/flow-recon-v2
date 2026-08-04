@echo off
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -e .
del /q data\recon-demo.sqlite 2>nul
recon discover --mock --from fixtures/demo_events.json --docs docs
recon recon --mock --fixture fixtures/sample_event.html --attendees data/attendees_example.csv --docs docs
echo.
echo ===============================================
echo  Hotovo. Ted uz jen:
echo    git add docs data ^&^& git commit -m "ukazkovy web" ^&^& git push
echo.
echo  Pak Settings -^> Pages -^> main / docs
echo ===============================================
pause
