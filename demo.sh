#!/usr/bin/env bash
# Spusti ukazku bez API klice. Data jsou SMYSLENA - vsechno se jmenuje UKAZKA.
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Chybi python3. Nainstaluj Python 3.10+."; exit 1; }

if [ ! -d .venv ]; then
  echo "→ Vytvarim virtualni prostredi..."
  python3 -m venv .venv
fi
source .venv/bin/activate
echo "→ Instaluji zavislosti..."
pip install -q -e ".[dev]"

echo "→ 1/3 discover"; recon discover --mock --from fixtures/demo_events.json
echo "→ 2/3 recon";    recon recon --mock --fixture fixtures/sample_event.html --attendees data/attendees_example.csv
echo "→ 3/3 watch";    recon watch >/dev/null

echo ""
echo "==============================================="
echo " Hotovo. Otevri v prohlizeci:"
echo "   $(pwd)/demo/index.html"
echo ""
echo " POZOR: vsechna data jsou smyslena (rok 2099)."
echo "==============================================="
