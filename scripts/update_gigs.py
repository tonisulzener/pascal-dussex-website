#!/usr/bin/env python3
"""Liest die Konzerttermine von den drei Band-Seiten und schreibt gigs.json.

Schlägt eine Quelle fehl (Seite nicht erreichbar oder Aufbau geändert),
bleiben die bisherigen Termine dieser Band erhalten und das Skript endet
mit Exit-Code 1, damit GitHub Actions eine Fehler-Mail verschickt.
"""
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "gigs.json"
UA = "Mozilla/5.0 (compatible; pascal-dussex-website gig updater)"

SOURCES = {
    "Soultrain": "https://www.dussexsoultrain.ch/kalender",
    "Les trois Suisses": "https://www.lestroissuisses.ch/tourdaten",
    "True Blue": "https://www.trueblue-jazz.com/konzerte",
}

MONTHS = {
    "jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12,
}


class SourceError(Exception):
    pass


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def text(fragment):
    fragment = re.sub(r"<br\s*/?>", " / ", fragment)
    s = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())
    return s.replace("« ", "«").replace(" »", "»")


def tidy(s):
    """«LAngnau» -> «Langnau», «WALD ZH» -> «Wald ZH», Kantonskürzel bleiben gross."""
    words = []
    for w in s.split(" "):
        if len(w) == 2 and w.isupper() and w.isalpha():
            words.append(w)  # ZH, BE, DE ...
        elif sum(c.isupper() for c in w) > 1:
            words.append("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")))
        else:
            words.append(w)
    return " ".join(words)


def parse_musikerseiten(page):
    """dussexsoultrain.ch und trueblue-jazz.com (Baukasten musikerseiten.de)."""
    if "class='calendar" not in page and 'class="calendar' not in page:
        raise SourceError("Kalender-Bereich nicht gefunden")
    gigs = []
    for li in re.findall(r"<li class=['\"]event row['\"]>(.*?)</li>", page, re.S):
        def field(cls):
            m = re.search(r"class=['\"]" + cls + r"['\"]>(.*?)</(?:p|h3|div)>", li, re.S)
            return text(m.group(1)) if m else ""
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", field("event__date"))
        if not m:
            continue
        date = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        venue = field("event__location")
        feat = re.search(r"feat\..*", field("event__title"))
        if feat:
            venue = f"{venue} · {feat.group(0)}" if venue else feat.group(0)
        gigs.append({"date": date.isoformat(), "place": tidy(field("event__city")), "venue": tidy(venue)})
    return gigs


def parse_squarespace_text(page):
    """lestroissuisses.ch: Termine als Fliesstext, z.B.
    «Fr. 23. Oktober 2026 / WANGEN-BRÜTTISELLEN, Gasthof Sternen, «Beiz» | kultur-kreis-wb.ch»"""
    gigs = []
    date_re = re.compile(r"^\w{2}\.?\s+(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]+)\.?\s+(\d{4})\s*/\s*(.*)$")
    for p in re.findall(r"<p[^>]*>(.*?)</p>", page, re.S):
        m = date_re.match(text(p))
        if not m:
            continue
        month = MONTHS.get(m.group(2)[:3].lower())
        if not month:
            continue
        date = dt.date(int(m.group(3)), month, int(m.group(1)))
        rest = m.group(4)
        parts = [x.strip(" ,") for x in re.split(r"\s*\|\s*", rest)]
        # parts[0] = «ORT, Lokal[, «Programm»]», danach Programm und/oder Website
        head = [x.strip() for x in parts[0].split(",") if x.strip()]
        place = tidy(head[0]) if head else ""
        venue_bits = head[1:]
        venue_bits += [x for x in parts[1:] if "«" in x]
        gigs.append({"date": date.isoformat(), "place": place, "venue": " · ".join(venue_bits)})
    return gigs


PARSERS = {
    "Soultrain": parse_musikerseiten,
    "Les trois Suisses": parse_squarespace_text,
    "True Blue": parse_musikerseiten,
}


def main():
    today = dt.date.today().isoformat()
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        old = []

    result, failures = [], []
    for band, url in SOURCES.items():
        previous = [g for g in old if g["band"] == band and g["date"] >= today]
        try:
            gigs = [g for g in PARSERS[band](fetch(url)) if g["date"] >= today]
            if not gigs and previous:
                raise SourceError("keine Termine mehr gefunden (vorher %d)" % len(previous))
            for g in gigs:
                g["band"] = band
            result += gigs
            print(f"{band}: {len(gigs)} Termine")
        except Exception as e:  # Netzwerk, Parser, alles: alte Daten behalten
            failures.append(band)
            result += previous
            print(f"FEHLER {band} ({url}): {e} – behalte {len(previous)} bisherige Termine", file=sys.stderr)

    result.sort(key=lambda g: (g["date"], g["band"]))
    new_json = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != new_json:
        OUT.write_text(new_json, encoding="utf-8")
        print("gigs.json aktualisiert")
    else:
        print("keine Änderungen")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
