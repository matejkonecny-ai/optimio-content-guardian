"""
Optimio Content Guardian — Streamlit App
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Optimio Content Guardian",
    page_icon="🔍",
    layout="wide",
)

# ── Logo ────────────────────────────────────────────────────────
if Path("optimio-logo-velke-cernobile.jpg").exists():
    st.sidebar.image("optimio-logo-velke-cernobile.jpg", use_container_width=True)
    st.sidebar.divider()

st.sidebar.title("🔍 Content Guardian")
st.sidebar.caption("Audit tónu komunikace webu Optimio")

# ── Cesty ────────────────────────────────────────────────────────
PAGES_FILE        = Path("pages.json")
AUDIT_RESULTS_FILE = Path("audit_results.json")
REPORT_FILE       = Path("report.html")
CRAWLER_SCRIPT    = Path("crawler.py")
AUDITOR_SCRIPT    = Path("auditor.py")

BASE_URL = "https://optimio-web.webflow.io"

# Přečti API klíč z Streamlit secrets nebo env proměnné
_api_key = st.secrets.get("ANTHROPIC_API_KEY", "") if hasattr(st, "secrets") else ""
if not _api_key:
    _api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if _api_key:
    os.environ["ANTHROPIC_API_KEY"] = _api_key

# ── Pomocné funkce ───────────────────────────────────────────────
def load_audit_results():
    if AUDIT_RESULTS_FILE.exists():
        return json.loads(AUDIT_RESULTS_FILE.read_text(encoding="utf-8"))
    return None

def score_color(score):
    if score >= 90: return "#27ae60"
    if score >= 70: return "#f1c40f"
    if score >= 40: return "#e67e22"
    return "#c0392b"

def score_label(score):
    if score >= 90: return "✅ Vyhovuje"
    if score >= 70: return "⚠️ Drobné odchylky"
    if score >= 40: return "🔶 Nevyhovuje"
    return "🔴 Zásadní nesoulad"

def score_bucket(score):
    if score >= 90: return "ok"
    if score >= 70: return "minor"
    if score >= 40: return "fail"
    return "critical"

# ── Sidebar: spuštění auditu ─────────────────────────────────────
st.sidebar.divider()
st.sidebar.markdown("### Nový audit")

target_url = st.sidebar.text_input("URL webu", value=BASE_URL)

st.sidebar.caption("⚠️ Spuštění auditu volá Anthropic API a spotřebuje kredity (~32 stránek).")
run_audit = st.sidebar.button("▶️ Spustit nový audit", type="primary", use_container_width=True,
                               help="Projde web a spustí AI analýzu (~3 min, spotřebuje API kredity)")

if run_audit:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.sidebar.error("Nastav ANTHROPIC_API_KEY v Streamlit secrets.")
    else:
        st.session_state["audit_running"] = True
        st.session_state["audit_log"] = []

# ── Stav posledního auditu ───────────────────────────────────────
results = load_audit_results()
if results:
    ts = results.get("timestamp", "")
    pages_count = len(results.get("pages", []))
    avg = results.get("avg_score", 0)
    st.sidebar.divider()
    st.sidebar.markdown(f"**Poslední audit:**")
    st.sidebar.caption(f"{ts}")
    st.sidebar.caption(f"{pages_count} stránek · průměr {avg:.0f} / 100")

# ── Hlavní obsah ─────────────────────────────────────────────────
st.title("🔍 Optimio Content Guardian")
st.markdown("AI audit obsahu webu — porovnání se strategií Tone of Voice")

# ── Probíhající audit ────────────────────────────────────────────
if st.session_state.get("audit_running"):
    st.info("Audit běží… Nejprve se projde web (crawl), pak AI zanalyzuje každou stránku.")
    log_box = st.empty()
    progress_bar = st.progress(0)

    with st.spinner("Stahuji stránky webu..."):
        # Crawl
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        crawl_proc = subprocess.run(
            [sys.executable, str(CRAWLER_SCRIPT)],
            capture_output=True, text=True, env=env
        )
        if crawl_proc.returncode != 0:
            st.error(f"Chyba crawleru:\n{crawl_proc.stderr}")
            st.session_state["audit_running"] = False
            st.stop()

    st.success(f"Web projit. Spouštím AI audit...")

    with st.spinner("AI analyzuje stránky..."):
        audit_proc = subprocess.run(
            [sys.executable, str(AUDITOR_SCRIPT), "--save-json"],
            capture_output=True, text=True, env=env
        )
        if audit_proc.returncode != 0:
            st.error(f"Chyba auditoru:\n{audit_proc.stderr}")
            st.session_state["audit_running"] = False
            st.stop()

    st.session_state["audit_running"] = False
    st.success("Audit dokončen!")
    st.rerun()

# ── Zobrazení výsledků ───────────────────────────────────────────
if results is None:
    # Zkusíme načíst z report.html (iframe fallback)
    if REPORT_FILE.exists():
        st.info("Zobrazuji poslední vygenerovaný report. Pro interaktivní zobrazení spusť nový audit tlačítkem v sidebaru.")
        import streamlit.components.v1 as components
        components.html(
            REPORT_FILE.read_text(encoding="utf-8"),
            height=900,
            scrolling=True,
        )
    else:
        st.info("Zatím žádná data. Klikni na **▶️ Spustit audit** v sidebaru.")
    st.stop()

# ── Interaktivní report ──────────────────────────────────────────
pages = results.get("pages", [])
scores = [p["audit"].get("skore", 0) for p in pages]
avg_score = results.get("avg_score", 0)
ok       = sum(1 for s in scores if s >= 90)
minor    = sum(1 for s in scores if 70 <= s < 90)
fail     = sum(1 for s in scores if 40 <= s < 70)
critical = sum(1 for s in scores if s < 40)

# Souhrné metriky
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Průměrné skóre", f"{avg_score:.0f} / 100")
m2.metric("✅ Vyhovuje", ok)
m3.metric("⚠️ Drobné", minor)
m4.metric("🔶 Nevyhovuje", fail)
m5.metric("🔴 Kritické", critical)
m6.metric("Stránek celkem", len(pages))

st.divider()

# Filtry
filter_opts = {
    "Všechny": "all",
    "🔴 Kritické (0–39)": "critical",
    "🔶 Nevyhovuje (40–69)": "fail",
    "⚠️ Drobné (70–89)": "minor",
    "✅ Vyhovuje (90+)": "ok",
}
filter_choice = st.radio("Zobrazit:", list(filter_opts.keys()), horizontal=True)
active_filter = filter_opts[filter_choice]

# Filtrování + řazení (nejhorší nahoře)
filtered = [p for p in pages
            if active_filter == "all"
            or score_bucket(p["audit"].get("skore", 0)) == active_filter]
filtered.sort(key=lambda p: p["audit"].get("skore", 0))

st.caption(f"Zobrazeno {len(filtered)} stránek")
st.divider()

# Karty
for item in filtered:
    page  = item["page"]
    audit = item["audit"]
    score = audit.get("skore", 0)
    color = score_color(score)
    label = score_label(score)
    url   = page.get("url", "")
    short_url = url.replace("https://optimio-web.webflow.io", "") or "/"

    with st.container():
        col_meta, col_score = st.columns([5, 1])

        with col_meta:
            st.markdown(
                f"**[{short_url}]({url})** &nbsp; "
                f"<span style='background:#1e3a5f;color:#8ec8ff;padding:2px 8px;"
                f"border-radius:10px;font-size:.8rem'>{page.get('divize','')}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"*{page.get('h1','(bez H1)')}*")

        with col_score:
            st.markdown(
                f"<div style='text-align:center'>"
                f"<div style='font-size:2rem;font-weight:700;color:{color}'>{score}</div>"
                f"<div style='font-size:.75rem;color:#888'>/ 100</div>"
                f"<div style='font-size:.8rem;margin-top:.2rem'>{label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Problémy a silné stránky
        problems = audit.get("problemy", [])
        goods    = audit.get("silne_stranky", [])

        if problems:
            st.markdown(
                " ".join(
                    f"<span style='background:#3a1a1a;color:#ff8080;padding:2px 8px;"
                    f"border-radius:4px;font-size:.82rem;margin:2px'>{p}</span>"
                    for p in problems
                ),
                unsafe_allow_html=True,
            )
        if goods:
            st.markdown(
                " ".join(
                    f"<span style='background:#1a3a1a;color:#80d080;padding:2px 8px;"
                    f"border-radius:4px;font-size:.82rem;margin:2px'>{g}</span>"
                    for g in goods
                ),
                unsafe_allow_html=True,
            )

        # Rewrite návrh
        rw = audit.get("rewrite", {})
        if rw.get("original") and rw.get("navrzeny"):
            with st.expander("Navržený přepis"):
                st.markdown(f"**Původní:** _{rw['original']}_")
                st.markdown(f"**Navržený:** {rw['navrzeny']}")
                if rw.get("duvod"):
                    st.caption(f"Důvod: {rw['duvod']}")

        st.divider()
