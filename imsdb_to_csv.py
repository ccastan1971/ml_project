#!/usr/bin/env python3
"""
IMSDb -> CSV scraper
- Crawls A–Z pages or specific URLs
- Follows "Movie Scripts/... Script.html" -> 'Read "..." Script' -> /scripts/... flow
- Extracts title, writers, genres (only for this movie), draft_info, and full script_text
- Robust against layout variants; can follow inner "html"/"read" link for the script
- Jupyter-friendly (parse_known_args) and exposes run_imsdb(...)

Usage (terminal):
  python imsdb_to_csv.py --outdir data --csv imsdb_scripts.csv --letters AS --max 10 --delay 1.5
  python imsdb_to_csv.py --urls "https://imsdb.com/Movie%20Scripts/Fight%20Club%20Script.html"
  python imsdb_to_csv.py --urls "https://imsdb.com/scripts/Fight-Club.html"

Notes:
- Educational/research use only. Be polite with delay.
Dependencies:
  pip install requests beautifulsoup4
"""

import argparse
import csv
import os
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://imsdb.com"
INDEX_ALL = f"{BASE}/all-scripts.html"
HEADERS = {
    "User-Agent": "IMSDbResearchBot/1.0 (+https://example.org/contact) Python requests"
}

# ------------------------- HTTP -------------------------
def http_get(url, session, retries=3, backoff=1.6, timeout=30):
    """GET with retry/backoff; returns Response or None."""
    for i in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 404):
                return r
        except requests.RequestException:
            pass
        time.sleep(backoff * (2 ** i))
    return None

# ------------------------- Index parsing -------------------------
def parse_links_from_index(html, base=BASE):
    """
    Grab BOTH:
      - /scripts/*.html (direct script pages)
      - /Movie Scripts/<Title> Script.html (info pages that contain the 'Read "..." Script' link)
    """
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base, href)
        if re.search(r"/scripts/.+\.html$", href):
            links.add(full)
        elif re.search(r"/Movie\s+Scripts/.+Script\.html$", href, re.I):
            links.add(full)
    return sorted(links)

def resolve_to_script_url(html, url):
    """
    If on a 'Movie Scripts/... Script.html' page, find a 'Read ... Script' style link and return it.
    Matches broader variants like: 'Read "Title" Script', 'Read Script', 'HTML Version', etc.
    """
    if re.search(r"/Movie\s+Scripts/.+Script\.html$", url, re.I):
        soup = BeautifulSoup(html, "html.parser")
        # 1) common 'Read ... Script'
        a = soup.find("a", href=True, string=re.compile(r"Read\s+.*Script", re.I))
        if a:
            return urljoin(url, a["href"])
        # 2) fallbacks: any link that mentions 'Read' or 'HTML'
        for cand in soup.find_all("a", href=True):
            text = cand.get_text(" ", strip=True)
            if re.search(r"\b(Read|HTML)\b", text, re.I):
                return urljoin(url, cand["href"])
    return url

# ------------------------- Utilities -------------------------
def clean_text(txt):
    txt = (txt or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in txt.split("\n"))

# ------------------------- Robust field extraction -------------------------
def extract_title_and_writers_from_title_tag(soup):
    """
    Extract a clean movie title and optional writers from the <title>.
    Handles e.g.:
      'Read "Title" Script - by X & Y'
      'Read the "Title" Screenplay by X and Y'
      'Title - by X, Y'
    """
    title_txt = (soup.title.text if soup.title else "").strip()
    if not title_txt:
        return None, []

    patterns = [
        r'Read\s+(?:the\s+)?[“"\'`]?(?P<title>.+?)[”"\'`]?\s+(?:Script|Screenplay)\b(?:\s*-\s*by\s*(?P<writers>.+))?$',
        r'Read\s+(?:the\s+)?[“"\'`]?(?P<title>.+?)[”"\'`]?\s+(?:Script|Screenplay)\s+by\s+(?P<writers>.+)$',
        r'^(?P<title>.+?)\s*-\s*by\s*(?P<writers>.+)$'
    ]
    for pat in patterns:
        m = re.search(pat, title_txt, re.I)
        if m:
            t = m.group("title").strip(' ‘’"')
            ws = m.groupdict().get("writers")
            writers = []
            if ws:
                parts = re.split(r'\s*(?:&|,| and )\s*', ws, flags=re.I)
                writers = [p.strip() for p in parts if p.strip()]
            return t, writers

    # Fallback: try to strip leading 'Read ... Script'
    m = re.search(r'[“"\'`]?(?P<title>.+?)[”"\'`]?(\s+\|\s+|$)', title_txt)
    return (m.group("title").strip(' ‘’"') if m else title_txt), []

GENRE_MENU_SET = {
    "Action","Adventure","Animation","Comedy","Crime","Drama","Family","Fantasy",
    "Film-Noir","Horror","Musical","Mystery","Romance","Sci-Fi","Short","Thriller","War","Western"
}

def extract_genres(soup):
    """
    Return only the genres for THIS movie.
    Searches near a 'Genres:' label or bold 'Genres:' blocks, and filters out the global site menu.
    """
    genres = []

    # Classic "Genres:" label
    label_node = soup.find(string=re.compile(r"\bGenres\s*:\s*", re.I))
    containers = []
    if label_node:
        p = label_node.find_parent()
        if p: containers.append(p)
        if p and p.find_next_sibling(): containers.append(p.find_next_sibling())

    # Bold/strong 'Genres:' patterns
    for b in soup.find_all(['b', 'strong']):
        if b.get_text(strip=True).lower().startswith("genres"):
            containers.append(b.parent)

    for box in containers:
        for a in box.find_all("a", href=re.compile(r"/genre/")):
            g = a.get_text(strip=True)
            if g:
                genres.append(g)

    genres = sorted(set(genres))
    if genres and set(genres) == GENRE_MENU_SET:
        return []
    return genres

def extract_script_text_from_script_page(soup, base_url):
    """
    Get the actual script text from a /scripts/*.html page.
    Handles:
      - <td class="scrtext"><pre>...</pre>
      - Any <pre> blocks
      - Alternative content containers
      - A nested 'html'/'read' link inside the script area, which we should follow
    Returns: (text, next_url_to_follow_or_None)
    """
    # Preferred: scrtext/pre
    text_blocks = []
    for td in soup.find_all(["td", "div"], {"class": re.compile(r"\bscrtext\b", re.I)}):
        pres = td.find_all("pre")
        if pres:
            for pre in pres:
                text_blocks.append(pre.get_text("\n"))
    if text_blocks:
        return clean_text("\n\n".join(text_blocks)), None

    # Alternative containers
    alt_containers = [
        {"name": "div", "attrs": {"id": re.compile(r"screenplay|script", re.I)}},
        {"name": "div", "attrs": {"class": re.compile(r"screenplay|script|content", re.I)}},
    ]
    for spec in alt_containers:
        for box in soup.find_all(spec["name"], spec["attrs"]):
            pres = box.find_all("pre")
            if pres:
                text = "\n\n".join(pre.get_text("\n") for pre in pres)
                return clean_text(text), None
            txt = box.get_text("\n", strip=True)
            if txt and len(txt.splitlines()) > 50:
                return clean_text(txt), None

    # Any <pre> on page
    for pre in soup.find_all("pre"):
        text_blocks.append(pre.get_text("\n"))
    if text_blocks:
        return clean_text("\n\n".join(text_blocks)), None

    # Look for a deeper "read/html" link anywhere in plausible content areas
    for area in soup.find_all(["div", "td"], {"class": re.compile(r"scrtext|content|main", re.I)}):
        for a in area.find_all("a", href=True):
            label = a.get_text(" ", strip=True)
            href = a["href"]
            if re.search(r"(read|html|script)", label, re.I) or re.search(r"/scripts/.+\.html$", href, re.I):
                return "", urljoin(base_url, href)

    # PDF-only (we return the URL; not parsed here)
    a_pdf = soup.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
    if a_pdf:
        return "", urljoin(base_url, a_pdf["href"])

    # Last resort: whole page (noisy)
    body = soup.get_text("\n")
    body = re.sub(r"\n{3,}", "\n\n", body)
    return clean_text(body), None

def extract_writers(soup, script_text=""):
    """
    Return writers as a list:
      - Prefer /writer/* links
      - Else read 'Writers:' label block (plain text or links)
      - Else scan header of script_text for 'Written by' lines
    """
    # 1) linked writers
    linked = {a.get_text(strip=True) for a in soup.find_all("a", href=re.compile(r"/writer/"))}
    linked = [n for n in linked if n]
    if linked:
        return sorted(linked)

    # 2) 'Writers:' / 'Writer:' blocks
    writers = []
    label = soup.find(string=re.compile(r"\bWriters?\s*:\s*", re.I))
    boxes = []
    if label:
        p = label.find_parent()
        if p: boxes.append(p)
        if p and p.find_next_sibling(): boxes.append(p.find_next_sibling())

    for b in soup.find_all(['b', 'strong']):
        if re.match(r"writers?\s*:?$", b.get_text(strip=True), re.I):
            boxes.append(b.parent)

    for box in boxes:
        # links first
        for a in box.find_all("a", href=re.compile(r"/writer/")):
            nm = a.get_text(strip=True)
            if nm:
                writers.append(nm)
        # plain text after the label
        tail = box.get_text(" ", strip=True)
        tail = re.sub(r"(?i)^writers?\s*:\s*", "", tail)
        parts = re.split(r"\s*(?:&|,| and )\s*", tail)
        for ptxt in parts:
            ptxt = ptxt.strip()
            if ptxt and len(ptxt) > 2 and not re.search(r"genres|read|script", ptxt, re.I):
                writers.append(ptxt)

    writers = [w for w in (n.strip() for n in writers) if w]
    if writers:
        return sorted(set(writers))

    # 3) scan header of script text
    if script_text:
        header = "\n".join(script_text.splitlines()[:80])
        m = re.search(r"(?im)^\s*(screenplay\s+by|written\s+by)\s*[:\-]?\s*(.+)$", header)
        if m:
            tail = m.group(2)
            parts = re.split(r"\s*(?:&|,| and )\s*", tail)
            parts = [p.strip(" .") for p in parts if p.strip()]
            if parts:
                return parts

    return []

def extract_record(html, url, session=None):
    """
    Parse a /scripts/*.html page. If a nested 'html/read' link is detected,
    follow it (requires session) and extract again.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Title & tentative writers from <title>
    title_from_tag, writers_from_title = extract_title_and_writers_from_title_tag(soup)

    # Genres and draft info first
    genres = extract_genres(soup)
    head_text = " ".join(soup.get_text("\n").splitlines()[:300])
    m = re.search(r"\b(\d{4})(?:-\d{2})?\s*(?:Draft|Final|Revision|Rev(?:ision)?)\b", head_text, re.I)
    draft_info = m.group(0) if m else ""

    # Script text (may need to follow inner link)
    script_text, next_url = extract_script_text_from_script_page(soup, url)
    if next_url and session is not None:
        r2 = http_get(next_url, session)
        if r2 and r2.status_code == 200:
            soup2 = BeautifulSoup(r2.text, "html.parser")
            t2, _ = extract_title_and_writers_from_title_tag(soup2)
            if t2 and not title_from_tag:
                title_from_tag = t2
            txt2, _ = extract_script_text_from_script_page(soup2, next_url)
            if txt2.strip():
                script_text = txt2
                url = next_url  # update to final source

    # Writers AFTER we have script_text (for fallback parsing)
    writers = extract_writers(soup, script_text=script_text) or writers_from_title

    # Title fallback from script text if needed
    if not title_from_tag and script_text:
        first_lines = [l.strip() for l in script_text.splitlines()[:10] if l.strip()]
        if first_lines:
            caps = [l for l in first_lines if re.search(r"[A-Z]", l) and l.upper() == l]
            title_from_tag = max(caps, key=len) if caps else first_lines[0]

    if title_from_tag:
        title_from_tag = re.sub(r"\s+", " ", title_from_tag).strip(' ‘’"')

    return {
        "source_url": url,
        "title": title_from_tag or "",
        "writers": writers,
        "genres": genres,
        "draft_info": draft_info,
        "script_text": script_text or ""
    }

# ------------------------- Collection -------------------------
def collect_links(session, letters=None):
    links = set()
    if letters:
        for L in letters:
            url = f"{BASE}/alphabetical/{L.upper()}"
            r = http_get(url, session)
            if r and r.status_code == 200:
                links.update(parse_links_from_index(r.text))
    else:
        r = http_get(INDEX_ALL, session)
        if r and r.status_code == 200:
            links.update(parse_links_from_index(r.text))
    return sorted(links)

# ------------------------- CSV helpers -------------------------
def open_csv(csv_path):
    write_header = not os.path.exists(csv_path)
    fp = open(csv_path, "a", encoding="utf-8", newline="")
    writer = csv.DictWriter(fp, fieldnames=[
        "title", "source_url", "writers", "genres", "draft_info", "script_text"
    ])
    if write_header:
        writer.writeheader()
    return fp, writer

def to_row(rec):
    return {
        "title": rec.get("title", ""),
        "source_url": rec.get("source_url", ""),
        "writers": "|".join(rec.get("writers", [])),
        "genres": "|".join(rec.get("genres", [])),
        "draft_info": rec.get("draft_info", ""),
        "script_text": rec.get("script_text", "")
    }

# ------------------------- Core runner (callable from notebooks) -------------------------
def run_imsdb(outdir="imsdb_out", csv_name="imsdb_scripts.csv", delay=1.5,
              max_items=0, letters="", urls=None, resume=False):
    """
    Programmatic entry-point for Python/Jupyter.
    Returns: (rows_written, csv_path)
    """
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, csv_name)
    csv_fp, csv_writer = open_csv(csv_path)

    # For resume: cache existing source_url values
    existing = set()
    if resume and os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("source_url"):
                        existing.add(row["source_url"])
        except Exception:
            pass

    session = requests.Session()

    # Build targets
    if urls:
        targets = list(dict.fromkeys(urls))  # dedupe, preserve order
    else:
        letters_list = list(letters) if letters else None
        print("Collecting script links...")
        links = collect_links(session, letters=letters_list)
        if not links:
            print("No links found. Exiting.")
            csv_fp.close()
            return 0, csv_path
        targets = links

    print(f"Found {len(targets)} candidate pages.")
    fetched = 0

    for i, url in enumerate(targets, 1):
        if max_items and fetched >= max_items:
            break

        if resume and url in existing:
            print(f"[{i}/{len(targets)}] SKIP (resume): {url}")
            continue

        print(f"[{i}/{len(targets)}] GET {url}")
        r = http_get(url, session)
        if not r or r.status_code != 200:
            print(f"  ! request failed (status={getattr(r, 'status_code', 'N/A')})")
            time.sleep(delay); continue

        # If it's a 'Movie Scripts/... Script.html' page, follow to the real script page
        final_url = resolve_to_script_url(r.text, url)
        if final_url != url:
            r2 = http_get(final_url, session)
            if not r2 or r2.status_code != 200:
                print("  ! couldn't follow 'Read Script' link")
                time.sleep(delay); continue
            url = final_url
            r = r2

        # Extract record; may follow an inner 'html/read' link if needed
        rec = extract_record(r.text, url, session=session)

        if not rec["script_text"].strip():
            print("  ! No script text detected after follow-ups, skipping.")
            time.sleep(delay); continue

        if not rec["genres"]:
            print("  ~ genres not found for this page (ok: some entries lack tags)")

        csv_writer.writerow(to_row(rec))
        fetched += 1
        time.sleep(delay)

    csv_fp.close()
    print(f"Done. Wrote {fetched} rows to: {csv_path}")
    return fetched, csv_path

# ------------------------- CLI (works in terminals AND Jupyter) -------------------------
def main():
    ap = argparse.ArgumentParser(description="Scrape IMSDb and export full scripts to CSV.")
    ap.add_argument("--outdir", default="imsdb_out", help="Output folder")
    ap.add_argument("--csv", default="imsdb_scripts.csv", help="CSV filename")
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds between HTTP requests")
    ap.add_argument("--max", type=int, default=0, help="Max number of scripts (0 = no limit)")
    ap.add_argument("--letters", default="", help="Only crawl titles starting with these letters (e.g., ASZ)")
    ap.add_argument("--urls", nargs="*", help="Explicit pages to fetch (script or 'Movie Scripts' pages)")
    ap.add_argument("--resume", action="store_true", help="Skip rows already present (by source_url)")
    # Jupyter-friendly:
    args, _ = ap.parse_known_args()

    run_imsdb(
        outdir=args.outdir,
        csv_name=args.csv,
        delay=args.delay,
        max_items=args.max,
        letters=args.letters,
        urls=args.urls,
        resume=args.resume
    )

if __name__ == "__main__":
    main()
