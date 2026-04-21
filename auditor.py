"""
Optimio Content Guardian — AI Auditor
Načte pages.json, audituje každou stránku proti STRATEGIE.md,
generuje report.html
"""

import json
import os
import re
import time
from pathlib import Path

import anthropic

# ── Konfigurace ────────────────────────────────────────────────
PAGES_FILE    = "pages.json"
STRATEGIE_FILE = "STRATEGIE.md"
REPORT_FILE   = "report.html"

# Stránky, které auditujeme (přeskočíme profily týmu, prázdné testy, kontakt)
SKIP_DIVIZE = {"Kontakt", "Kariéra", "Obecné"}
SKIP_URL_FRAGMENTS = ["/nas-tym/", "/clanky/", "/kategorie/", "test-pro-oceneni",
                      "dalsi-blog", "dalsi-oceneni", "zkouska"]

# ── Načtení strategie ───────────────────────────────────────────
strategie_text = Path(STRATEGIE_FILE).read_text(encoding="utf-8")

# ── Anthropic klient ────────────────────────────────────────────
client = anthropic.Anthropic()  # čte ANTHROPIC_API_KEY z env

# ── Systémový prompt ────────────────────────────────────────────
SYSTEM_PROMPT = f"""Jsi AI auditor obsahu pro agenturu Optimio.
Tvým úkolem je auditovat texty z webu Optimio a porovnávat je
s níže uvedenou komunikační strategií.

=== KOMUNIKAČNÍ STRATEGIE OPTIMIO ===
{strategie_text}
=== KONEC STRATEGIE ===

Při každém auditu:
1. Ohodnoť text skóre 0–100 dle škály ze strategie.
2. Identifikuj konkrétní problémy (zakázaná slova, dodavatelský tón, chybějící byznysový dopad).
3. Navrhni rewrite klíčové části (H1, první odstavec nebo nejproblematičtější větu).

Odpovídej VÝHRADNĚ v JSON formátu – bez markdown bloků, bez komentářů mimo JSON.
"""

AUDIT_PROMPT = """Audituj tuto stránku z webu Optimio:

URL: {url}
Divize: {divize}
Titulek: {title}
H1: {h1}

Nadpisy:
{headings}

Texty:
{paragraphs}

Vrať JSON v PŘESNĚ tomto formátu:
{{
  "skore": <číslo 0-100>,
  "hodnoceni": "<✅ Vyhovuje | ⚠️ Drobné odchylky | 🔶 Nevyhovuje | 🔴 Zásadní nesoulad>",
  "problemy": ["<konkrétní problém 1>", "<konkrétní problém 2>"],
  "silne_stranky": ["<co funguje dobře>"],
  "rewrite": {{
    "original": "<původní text k přepsání>",
    "navrzeny": "<navržený přepis>",
    "duvod": "<proč tato změna>"
  }}
}}
"""

def should_skip(page: dict) -> bool:
    if page["divize"] in SKIP_DIVIZE:
        return True
    for fragment in SKIP_URL_FRAGMENTS:
        if fragment in page["url"]:
            return True
    return False

def format_headings(headings: list) -> str:
    return "\n".join(f"  {h['level'].upper()}: {h['text']}" for h in headings[:8])

def format_paragraphs(paragraphs: list) -> str:
    selected = paragraphs[:6]
    return "\n\n".join(f"  • {p[:400]}" for p in selected)

def audit_page(page: dict) -> dict:
    prompt = AUDIT_PROMPT.format(
        url        = page["url"],
        divize     = page["divize"],
        title      = page.get("title", ""),
        h1         = page.get("h1", ""),
        headings   = format_headings(page.get("headings", [])),
        paragraphs = format_paragraphs(page.get("paragraphs", [])),
    )

    message = client.messages.create(
        model      = "claude-sonnet-4-6",
        max_tokens = 1500,
        system     = SYSTEM_PROMPT,
        messages   = [{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Vyčisti případné markdown bloky
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)

# ── HTML report ─────────────────────────────────────────────────
HTML_HEAD = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Optimio Content Guardian — Report</title>
<style>
  :root {
    --bg: #0f1117; --card: #1a1f2e; --border: #2a3a5a;
    --green: #27ae60; --yellow: #f39c12; --orange: #e67e22; --red: #c0392b;
    --blue: #4a9eff; --text: #e0e0e0; --muted: #888;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 2rem; }
  h1 { font-size: 1.8rem; margin-bottom: .3rem; }
  .subtitle { color: var(--muted); margin-bottom: 2rem; font-size: .95rem; }
  .summary { display: flex; gap: 1rem; margin-bottom: 2.5rem; flex-wrap: wrap; }
  .stat { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.5rem; min-width: 140px; }
  .stat-num { font-size: 2rem; font-weight: 700; }
  .stat-label { color: var(--muted); font-size: .85rem; margin-top: .2rem; }
  .filters { margin-bottom: 1.5rem; display: flex; gap: .5rem; flex-wrap: wrap; }
  .filter-btn { background: var(--card); border: 1px solid var(--border); color: var(--text); padding: .4rem 1rem; border-radius: 20px; cursor: pointer; font-size: .85rem; }
  .filter-btn.active, .filter-btn:hover { background: var(--blue); border-color: var(--blue); }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.2rem; }
  .card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
  .card-meta { flex: 1; }
  .card-url { font-size: .8rem; color: var(--blue); text-decoration: none; word-break: break-all; }
  .card-url:hover { text-decoration: underline; }
  .card-divize { display: inline-block; background: #1e3a5f; color: #8ec8ff; padding: .2rem .7rem; border-radius: 12px; font-size: .78rem; margin: .4rem 0; }
  .card-h1 { font-size: 1.05rem; font-weight: 600; margin-top: .3rem; }
  .score-badge { text-align: center; min-width: 80px; }
  .score-num { font-size: 2.2rem; font-weight: 700; line-height: 1; }
  .score-label { font-size: .75rem; color: var(--muted); margin-top: .2rem; }
  .score-green { color: var(--green); }
  .score-yellow { color: #f1c40f; }
  .score-orange { color: var(--orange); }
  .score-red { color: var(--red); }
  .section-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: .5rem; margin-top: 1rem; }
  .tag { display: inline-block; padding: .2rem .6rem; border-radius: 4px; font-size: .8rem; margin: .2rem .2rem .2rem 0; }
  .tag-problem { background: #3a1a1a; color: #ff8080; border: 1px solid #5a2a2a; }
  .tag-good { background: #1a3a1a; color: #80ff80; border: 1px solid #2a5a2a; }
  .rewrite-box { background: #0d1117; border-radius: 8px; padding: 1rem; margin-top: 1rem; border: 1px solid var(--border); }
  .rewrite-original { color: #ff9090; font-style: italic; margin-bottom: .6rem; font-size: .9rem; line-height: 1.5; }
  .rewrite-arrow { color: var(--muted); font-size: .8rem; margin-bottom: .5rem; }
  .rewrite-new { color: #90ff90; font-size: .9rem; line-height: 1.5; font-weight: 500; }
  .rewrite-reason { color: var(--muted); font-size: .8rem; margin-top: .6rem; border-top: 1px solid var(--border); padding-top: .5rem; }
  .hodnoceni-badge { font-size: .85rem; padding: .3rem .8rem; border-radius: 20px; display: inline-block; }
  .divider { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
</style>
</head>
<body>
<h1>🔍 Optimio Content Guardian</h1>
<p class="subtitle">AI audit obsahu webu · porovnání se strategií Tone of Voice</p>
"""

HTML_TAIL = """
<script>
function filterCards(val) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === val));
  document.querySelectorAll('.audit-card').forEach(card => {
    const show = val === 'all' || card.dataset.score === val;
    card.style.display = show ? '' : 'none';
  });
}
document.addEventListener('DOMContentLoaded', () => filterCards('all'));
</script>
</body></html>
"""

def score_class(score: int) -> str:
    if score >= 90: return "score-green"
    if score >= 70: return "score-yellow"
    if score >= 40: return "score-orange"
    return "score-red"

def score_bucket(score: int) -> str:
    if score >= 90: return "ok"
    if score >= 70: return "minor"
    if score >= 40: return "fail"
    return "critical"

def render_card(page: dict, audit: dict) -> str:
    score  = audit.get("skore", 0)
    sc     = score_class(score)
    bucket = score_bucket(score)
    url    = page["url"]

    problems = "".join(f'<span class="tag tag-problem">{p}</span>'
                       for p in audit.get("problemy", []))
    goods    = "".join(f'<span class="tag tag-good">{g}</span>'
                       for g in audit.get("silne_stranky", []))

    rw = audit.get("rewrite", {})
    rewrite_html = ""
    if rw.get("original") and rw.get("navrzeny"):
        rewrite_html = f"""
        <div class="rewrite-box">
          <div class="section-title">Navržený přepis</div>
          <div class="rewrite-original">❌ {rw['original']}</div>
          <div class="rewrite-arrow">↓ nahradit za</div>
          <div class="rewrite-new">✅ {rw['navrzeny']}</div>
          <div class="rewrite-reason">💡 {rw.get('duvod','')}</div>
        </div>"""

    return f"""
<div class="card audit-card" data-score="{bucket}">
  <div class="card-header">
    <div class="card-meta">
      <a class="card-url" href="{url}" target="_blank">{url.replace('https://optimio-web.webflow.io','')}</a>
      <div><span class="card-divize">{page['divize']}</span></div>
      <div class="card-h1">{page.get('h1','(bez H1)')}</div>
    </div>
    <div class="score-badge">
      <div class="score-num {sc}">{score}</div>
      <div class="score-label">/ 100</div>
      <div style="margin-top:.4rem;font-size:.9rem">{audit.get('hodnoceni','')}</div>
    </div>
  </div>
  <hr class="divider">
  {('<div class="section-title">Problémy</div>' + problems) if problems else ''}
  {('<div class="section-title" style="margin-top:.8rem">Co funguje</div>' + goods) if goods else ''}
  {rewrite_html}
</div>"""

# ── Hlavní běh ──────────────────────────────────────────────────
def main(save_json: bool = False):
    pages = json.loads(Path(PAGES_FILE).read_text(encoding="utf-8"))

    to_audit = [p for p in pages if not should_skip(p)]
    print(f"Auduji {len(to_audit)} stránek (z {len(pages)} celkem)...")
    print()

    results = []
    for i, page in enumerate(to_audit, 1):
        label = page["url"].replace("https://optimio-web.webflow.io", "") or "/"
        print(f"  [{i:02d}/{len(to_audit)}] {page['divize']:<30} {label}")
        try:
            audit = audit_page(page)
            results.append((page, audit))
        except Exception as e:
            print(f"         CHYBA: {e}")
            results.append((page, {"skore": 0, "hodnoceni": "⚠️ Chyba auditu",
                                   "problemy": [str(e)], "silne_stranky": [], "rewrite": {}}))
        time.sleep(0.5)

    # Statistiky
    scores    = [r[1].get("skore", 0) for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0
    ok        = sum(1 for s in scores if s >= 90)
    minor     = sum(1 for s in scores if 70 <= s < 90)
    fail      = sum(1 for s in scores if 40 <= s < 70)
    critical  = sum(1 for s in scores if s < 40)

    print(f"\n── Výsledky ────────────────────────────────────")
    print(f"  Průměrné skóre:  {avg_score:.0f} / 100")
    print(f"  ✅ Vyhovuje:      {ok}")
    print(f"  ⚠️  Drobné:        {minor}")
    print(f"  🔶 Nevyhovuje:    {fail}")
    print(f"  🔴 Kritické:      {critical}")

    # Seřazení: nejhorší nahoře
    results.sort(key=lambda x: x[1].get("skore", 0))

    # Generování HTML
    summary_html = f"""
<div class="summary">
  <div class="stat"><div class="stat-num">{avg_score:.0f}</div><div class="stat-label">Průměrné skóre</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--green)">{ok}</div><div class="stat-label">✅ Vyhovuje (90+)</div></div>
  <div class="stat"><div class="stat-num" style="color:#f1c40f">{minor}</div><div class="stat-label">⚠️ Drobné (70–89)</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--orange)">{fail}</div><div class="stat-label">🔶 Nevyhovuje (40–69)</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--red)">{critical}</div><div class="stat-label">🔴 Kritické (0–39)</div></div>
  <div class="stat"><div class="stat-num">{len(results)}</div><div class="stat-label">Auditovaných stránek</div></div>
</div>
<div class="filters">
  <button class="filter-btn active" data-filter="all" onclick="filterCards('all')">Všechny</button>
  <button class="filter-btn" data-filter="critical" onclick="filterCards('critical')">🔴 Kritické</button>
  <button class="filter-btn" data-filter="fail" onclick="filterCards('fail')">🔶 Nevyhovuje</button>
  <button class="filter-btn" data-filter="minor" onclick="filterCards('minor')">⚠️ Drobné</button>
  <button class="filter-btn" data-filter="ok" onclick="filterCards('ok')">✅ Vyhovuje</button>
</div>"""

    cards_html = "\n".join(render_card(p, a) for p, a in results)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(HTML_HEAD + summary_html + cards_html + HTML_TAIL)

    print(f"\n✅ Report uložen do {REPORT_FILE}")
    print(f"   Otevři: file://{Path(REPORT_FILE).resolve()}")

    if save_json:
        import datetime
        audit_data = {
            "timestamp": datetime.datetime.now().strftime("%d. %m. %Y %H:%M"),
            "avg_score": round(avg_score, 1),
            "pages": [
                {"page": p, "audit": a}
                for p, a in results
            ],
        }
        with open("audit_results.json", "w", encoding="utf-8") as f:
            json.dump(audit_data, f, ensure_ascii=False, indent=2)
        print(f"✅ audit_results.json uložen.")

if __name__ == "__main__":
    import sys
    save_json = "--save-json" in sys.argv
    main(save_json=save_json)
