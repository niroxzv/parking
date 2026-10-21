"""Scrape Singapore parking-lot sale/rent listings from property websites.

Usage:
    pip install requests beautifulsoup4
    python scrape_parking.py

Output: parking_listings.csv next to this script.
Only fetches pages allowed by each site's robots.txt, with a delay between requests.
Sites that render listings with JavaScript or block bots will return little; check
the "skipped" log lines and respect each site's terms of use.
"""
import csv
import re
import time
import urllib.robotparser as rp
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

OUT = Path(__file__).parent
UA = "Mozilla/5.0 (compatible; ParkingResearchBot/1.0; personal research)"
DELAY = 3  # seconds between requests
IGNORE_ROBOTS = True  # set False to honour each site's robots.txt

# Add or remove sites here. Each entry: name, start URLs, and a regex that
# detail-page links must match.
SOURCES = [
    # link_re=None parses the start page itself; otherwise follows matching links.
    {"name": "Far East Malls - Orchard Central", "start": ["https://fareastmalls.com.sg/orchard-central/Getting-there"], "link_re": None},
    {"name": "Far East Malls - Icon Village", "start": ["https://fareastmalls.com.sg/icon-village/Getting-there"], "link_re": None},
    {"name": "Far East Malls - Hougang 1", "start": ["https://fareastmalls.com.sg/hougang-1/Getting-there"], "link_re": None},
    {"name": "EdgeProp", "start": ["https://www.edgeprop.sg/"], "link_re": r"(carpark|parking)"},
    {"name": "99.co", "start": ["https://www.99.co/singapore/"], "link_re": r"(carpark|parking)"},
    {"name": "PropertyGuru", "start": ["https://www.propertyguru.com.sg/"], "link_re": r"(carpark|parking)"},
]

PHONE_RE = re.compile(r"(?<!\d)(?:\+?65[\s-]?)?([689]\d{3}[\s-]?\d{4})(?!\d)")
PRICE_RE = re.compile(r"S?\$\s?([\d,]+(?:\.\d+)?)\s*(?:/|per)?\s*(mth|month|year|yr|lot)?", re.I)
LOTS_RE = re.compile(r"(\d{1,5})\s*(?:lots?|bays?|parking (?:spaces|lots)|carpark (?:lots|spaces))", re.I)

_robots = {}
session = requests.Session()
session.headers["User-Agent"] = UA


def allowed(url):
    if IGNORE_ROBOTS:
        return True
    root = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if root not in _robots:
        parser = rp.RobotFileParser(root + "/robots.txt")
        try:
            parser.read()
        except Exception:
            parser = None
        _robots[root] = parser
    parser = _robots[root]
    return parser is None or parser.can_fetch(UA, url)


def fetch(url):
    if not allowed(url):
        print("skipped (robots.txt):", url)
        return None
    time.sleep(DELAY)
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print("skipped (%s): %s" % (e, url))
        return None


def parse_detail(source, url, html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if not re.search(r"car\s?park|parking", text, re.I):
        return None
    title = (soup.title.string or "").strip() if soup.title else ""
    phones = {m.group(1).replace(" ", "").replace("-", "") for m in PHONE_RE.finditer(text)}
    phones |= {a["href"][4:] for a in soup.select('a[href^="tel:"]')}
    prices = [m.group(0).strip() for m in PRICE_RE.finditer(text)][:5]
    lots = LOTS_RE.search(text)
    return {
        "source": source,
        "url": url,
        "title": title,
        "price_mentions": " | ".join(prices),
        "lots_mentioned": lots.group(1) if lots else "",
        "phones": " | ".join(sorted(phones)),
    }


def scrape_sources():
    rows, seen = [], set()
    for src in SOURCES:
        link_re = re.compile(src["link_re"], re.I) if src["link_re"] else None
        for start in src["start"]:
            html = fetch(start)
            if not html:
                continue
            if link_re is None:
                row = parse_detail(src["name"], start, html)
                if row:
                    rows.append(row)
                continue
            soup = BeautifulSoup(html, "html.parser")
            links = {urljoin(start, a["href"]) for a in soup.select("a[href]")}
            for link in sorted(l for l in links if link_re.search(l)):
                if link in seen:
                    continue
                seen.add(link)
                page = fetch(link)
                row = parse_detail(src["name"], link, page) if page else None
                if row:
                    rows.append(row)
    return rows


if __name__ == "__main__":
    rows = scrape_sources()
    path = OUT / "parking_listings.csv"
    if rows:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print("wrote %d rows to %s" % (len(rows), path))
