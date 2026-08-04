# Jak to dostat na GitHub — všechno v prohlížeči

Za 15 minut budeš mít funkční odkaz `https://<tvoje-jméno>.github.io/flow-event-recon/`,
který můžeš poslat kolegům.

**Nepotřebuješ terminál ani nic instalovat.** Python i generování webu běží na GitHubu.
Jediné, co děláš u sebe, je nahrání souborů — a to jde přetažením myší.

Repozitář musí být **Public**. GitHub Pages jsou na Free plánu jen ve veřejných
repozitářích. Kód je obecný nástroj, na tom nic není. Kdybys ho chtěl privátní,
GitHub Pro za 4 $/měsíc umí Pages i z privátního repa.

---

## Krok 1 — Nahraj soubory (5 min)

### 1a. Založ repozitář

Jdi na **github.com/new**:

| Pole | Hodnota |
|---|---|
| Repository name | `flow-event-recon` |
| Visibility | **Public** |
| Add a README file | **zaškrtni** — ať repo není prázdné |

**Create repository**.

### 1b. Nahraj obsah zipu

Rozbal `flow-event-recon.zip`. Vznikne složka `event-recon-agent`.

V repu klikni **Add file** → **Upload files**.
Otevři složku `event-recon-agent`, **označ všechno uvnitř** (Ctrl+A / Cmd+A)
a přetáhni to do okna prohlížeče.

> Přetahuj **obsah** složky, ne složku samotnou. Jinak se všechno zanoří
> o úroveň níž a nic nepojede.

Dole napiš `Flow Event Recon` a **Commit changes**.

### 1c. Zkontroluj jednu věc

V seznamu souborů se podívej, jestli vidíš složku **`.github`**.

**Vidíš ji** → jdi na krok 2.

**Nevidíš ji** → prohlížeč vynechal složky začínající tečkou. Oprava trvá minutu:

1. **Add file** → **Create new file**
2. Do políčka s názvem napiš přesně `.github/workflows/recon.yml`
   (lomítka sama vytvoří složky)
3. Otevři si v repu soubor **`workflow-zaloha.txt`**, zkopíruj z něj všechno
   pod čarou a vlož to sem
4. **Commit changes**

---

## Krok 2 — Povol Actions zapisovat (1 min)

**Udělej to dřív, než něco spustíš.** Bez tohohle spadne každý běh na chybě `403`
a je to zdaleka nejčastější problém.

**Settings** → v levém menu **Actions** → **General** → sjeď dolů na
**Workflow permissions** → vyber **Read and write permissions** → **Save**.

---

## Krok 3 — Zapni Pages (2 min)

**Settings** → v levém menu **Pages**.

| Pole | Nastav na |
|---|---|
| Source | `Deploy from a branch` |
| Branch | `main` |
| Folder | **`/docs`** — ne `/root` |

**Save.**

Za 1–2 minuty je web na `https://<tvoje-jméno>.github.io/flow-event-recon/`.
Ukázkový web je v balíčku předgenerovaný, takže tam něco uvidíš hned.

**Tenhle odkaz můžeš poslat kolegům.**

---

## Krok 4 — Ověř, že kód reálně běží (1 min)

Tímhle si ověříš, že to funguje jako nástroj — ne že jen koukáš na hotové
soubory z balíčku.

**Actions** → vlevo **Flow Event Recon** → vpravo **Run workflow**
→ v menu **Co udělat** nech `ukazka` → zelené **Run workflow**.

Za minutu doběhne. V souhrnu běhu ti vypíše odkaz na web.
Zelená fajfka = Python kód proběhl na GitHubu a přepsal `docs/`.

Červený křížek → otevři běh a podívej se, na čem spadl. Skoro vždy je to
nedodělaný krok 2.

---

## Krok 5 — Vlož Claude API klíč (1 min)

**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Secret |
|---|---|
| `ANTHROPIC_API_KEY` | klíč od Etnetery |

Název musí sedět přesně, včetně velkých písmen.

---

## Krok 6 — Vyplň, kdo jste (3 min)

Bez tohohle budou věty „o čem s tím člověkem mluvit" k ničemu.

V repu klikni na `config` → `icp.yaml` → ikona **tužky** vpravo nahoře.
Najdi položku `positioning` — je tam `TODO`.

Napiš 3–4 věty: kdo jste, co děláte, jaké máte reference, jaké lidi hledáte.
Z tohohle textu Claude generuje angle věty, takže **piš jen to, co je pravda**.

Ve stejném souboru zkontroluj `organizer_watchlist`. To jsou moje domněnky,
ne vaše znalost — dávají +10 bodů, takže hýbou pořadím.

Dole **Commit changes**.

---

## Krok 7 — První ostrý recon

**Actions** → **Flow Event Recon** → **Run workflow**:

| Pole | Vyplň |
|---|---|
| Co udělat | `recon` |
| URL eventu | odkaz na reálnou konferenci |
| Cesta k CSV | nech prázdné, nebo cestu k exportu z event app |
| deep | zaškrtni, ať Claude dohledá firmy |

**Run workflow**. Za 1–2 minuty obnov svůj Pages odkaz.

Hledání nových eventů je ten samý workflow, jen **Co udělat** = `discover`.
Ten běží i sám každé pondělí ráno v 7:00.

---

## Když to nefunguje

| Co vidíš | Co s tím |
|---|---|
| Pages hodí 404 | Špatná složka. Settings → Pages → Folder musí být `/docs`. Nebo ještě neproběhl deploy — počkej 2 min. |
| `403` v Actions | Krok 2. Settings → Actions → General → Read and write permissions. |
| V Actions není žádný workflow | Chybí složka `.github`. Viz krok 1c. |
| Web ukazuje starou verzi | Cache prohlížeče. Ctrl+Shift+R. |
| `Chybi ANTHROPIC_API_KEY` | Krok 5, nebo překlep v názvu secretu. |
| Recon nenašel žádné speakery | Web konference je nejspíš v JavaScriptu. Ulož stránku jako HTML, nahraj do `fixtures/` a spusť lokálně s `--fixture`. |
| Actions došly minuty | Free plán má 2 000 min/měsíc. Běhy jsou krátké, ale pondělní cron to ukrajuje. |

---

## Jak z toho vytáhnout nejvíc

1. **Export účastníků z event app** (Swapcard, Brella, Whova) — největší jediný
   přínos. Web eventu ukáže 6 speakerů, app 200 lidí. Ulož jako CSV se sloupci
   `name,title,company`, nahraj do složky `data/` a v workflow vyplň cestu.
2. **Zaškrtni `deep`** — Claude si dohledá obor a velikost firem přes web search.
3. **Doplň key accounts** v `config/key_accounts.csv`. Stačí název a doména.

---

## Zpětná vazba od kolegů

Nejužitečnější formát: *„tenhle člověk má 51, měl by mít ~85, protože…"*

U každého čísla na webu je tlačítko **„Proč tohle číslo?"** s rozpadem bodů.
Z toho poznám, která váha v rubrice je špatně, a opravím ji v `config/icp.yaml` —
v kódu se sahat nemusí na nic.

---

## Pro ty, co umí terminál

Krok 1 jde i takhle:

```bash
cd event-recon-agent
git init && git add . && git commit -m "Flow Event Recon"
git remote add origin https://github.com/<jméno>/flow-event-recon.git
git branch -M main && git push -u origin main
```

A celý nástroj jde spustit lokálně bez GitHubu:

```bash
pip install -e .
recon discover --mock --from fixtures/demo_events.json --docs docs
```
