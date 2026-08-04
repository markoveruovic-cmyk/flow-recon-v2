#!/usr/bin/env bash
# Vygeneruje UKAZKOVY web primo do docs/, aby sel hned publikovat na GitHub Pages.
# Data jsou smyslena - stranky maji cerveny pruh "Ukazkova data".
set -e
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -e .

rm -f data/recon-demo.sqlite
recon discover --mock --from fixtures/demo_events.json --docs docs
recon recon --mock --fixture fixtures/sample_event.html \
  --attendees data/attendees_example.csv --docs docs

echo ""
echo "==============================================="
echo " Hotovo. Ted uz jen:"
echo "   git add docs data && git commit -m 'ukazkovy web' && git push"
echo ""
echo " Pak Settings -> Pages -> main / docs"
echo "==============================================="
