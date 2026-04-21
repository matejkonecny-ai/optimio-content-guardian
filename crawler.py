"""
Optimio Content Guardian — Crawler
Prochází web Optimio, extrahuje texty a přiřazuje divize.
Výstup: pages.json
"""

import json
import time
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://optimio-web.webflow.io"

# Mapování URL segmentů → divize
DIVIZE_MAP = {
    "interim-cmo":        "Strategie / Interim CMO",
    "ppc":                "PPC",
    "social-ads":         "PPC / Social Ads",
    "brand-building":     "PPC / Brand Building",
    "rtb":                "PPC / RTB",
    "videokampane":       "PPC / Video",
    "zbozove-srovnavace": "PPC / Srovnávače",
    "digital-advertising":"PPC / Digital Advertising",
    "digitalni-strategie":"Strategie",
    "web-a-seo":          "SEO",
    "seo-aio-audit":      "SEO",
    "creative":           "Kreativa",
    "data":               "Data & Analytika",
    "media":              "Média",
    "retention-cx":       "Retention & CX",
    "ux-research":        "UX Research",
    "ux-audit":           "UX Research",
    "reference":          "Reference (case study)",
    "blog":               "Blog",
    "o-nas":              "O nás",
    "kariera":            "Kariéra",
    "kontakt":            "Kontakt",
    "zkusenosti":         "Zkušenosti / Reviews",
    "nase-sluzby":        "Přehled služeb",
}

def detect_divize(url: str) -> str:
    path = urlparse(url).path.lower().strip("/")
    segments = path.split("/")
    # Hledáme od nejkonkrétnějšího segmentu
    for segment in reversed(segments):
        if segment in DIVIZE_MAP:
            return DIVIZE_MAP[segment]
    if not path:
        return "Homepage"
    return "Obecné"

def extract_text(soup: BeautifulSoup) -> dict:
    """Extrahuje strukturovaný obsah ze stránky."""

    # Odstraň navigaci, footer, skripty, styly
    for tag in soup(["script", "style", "nav", "footer",
                     "noscript", "svg", "iframe"]):
        tag.decompose()

    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else ""

    # H1
    h1 = soup.find("h1")
    h1_text = h1.get_text(strip=True) if h1 else ""

    # Všechny nadpisy
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 3:
            headings.append({"level": tag.name, "text": text})

    # Odstavce a blokový text — minimální délka 40 znaků
    paragraphs = []
    for tag in soup.find_all(["p", "li", "blockquote"]):
        text = tag.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        if len(text) >= 40:
            paragraphs.append(text)

    # Deduplikace
    paragraphs = list(dict.fromkeys(paragraphs))

    # Celý čistý text (pro AI kontext)
    main = soup.find("main") or soup.find("body")
    full_text = ""
    if main:
        full_text = re.sub(r"\s+", " ", main.get_text(separator=" ", strip=True))

    return {
        "title":      title_text,
        "h1":         h1_text,
        "headings":   headings,
        "paragraphs": paragraphs,
        "full_text":  full_text[:6000],  # limit pro AI
    }

def get_internal_links(soup: BeautifulSoup, base: str) -> set:
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        full = urljoin(base, href)
        parsed = urlparse(full)
        # Pouze stejná doména
        if parsed.netloc == urlparse(base).netloc:
            # Bez fragmentů a query
            clean = parsed.scheme + "://" + parsed.netloc + parsed.path.rstrip("/")
            links.add(clean)
    return links

def crawl(start_url: str, max_pages: int = 60) -> list:
    visited  = set()
    to_visit = {start_url.rstrip("/")}
    results  = []
    session  = requests.Session()
    session.headers["User-Agent"] = "OptimioContentGuardian/1.0"

    print(f"Startuji crawl: {start_url}")
    print("-" * 60)

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"  [SKIP {resp.status_code}] {url}")
                continue
            if "text/html" not in resp.headers.get("Content-Type", ""):
                continue
        except Exception as e:
            print(f"  [CHYBA] {url} — {e}")
            continue

        soup    = BeautifulSoup(resp.text, "html.parser")
        content = extract_text(soup)
        divize  = detect_divize(url)

        # Přeskočit stránky bez obsahu
        if not content["h1"] and not content["paragraphs"]:
            print(f"  [PRÁZDNÁ] {url}")
            continue

        page = {
            "url":    url,
            "divize": divize,
            **content,
        }
        results.append(page)

        # Nové linky ke zpracování
        new_links = get_internal_links(soup, url)
        to_visit.update(new_links - visited)

        print(f"  [{len(results):02d}] {divize:<30} {url.replace(BASE_URL,'')}")
        time.sleep(0.4)  # slušné chování vůči serveru

    print("-" * 60)
    print(f"Hotovo. Nalezeno {len(results)} stránek s obsahem.")
    return results

if __name__ == "__main__":
    pages = crawl(BASE_URL)

    with open("pages.json", "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)

    print(f"\nUloženo do pages.json ({len(pages)} stránek).")

    # Rychlý přehled divizí
    from collections import Counter
    divize_counts = Counter(p["divize"] for p in pages)
    print("\nPřehled dle divize:")
    for divize, count in sorted(divize_counts.items()):
        print(f"  {count:2d}×  {divize}")
