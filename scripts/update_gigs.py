#!/usr/bin/env python3
"""Liest die Konzerttermine von den Band- und Projekt-Seiten und schreibt gigs.json.

Schlägt eine Quelle fehl (Seite nicht erreichbar oder Aufbau geändert),
bleiben die bisherigen Termine dieser Band erhalten und das Skript endet
mit Exit-Code 1, damit GitHub Actions eine Fehler-Mail verschickt.
"""
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "gigs.json"
UA = "Mozilla/5.0 (compatible; pascal-dussex-website gig updater)"


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


CASINO = "https://www.casinotheater.ch/spielplan/produktion/"
MONTHS_SHORT = {"jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
                "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12}


def ld_events(page):
    """Alle schema.org-Events aus den JSON-LD-Blöcken einer Seite."""
    events = []
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        events += [e for e in items if isinstance(e, dict) and "Event" in str(e.get("@type", ""))]
    return events


def src_bundesordner():
    """casinotheater.ch: Vorstellungen in Winterthur und Tour-Daten, alle einzeln."""
    gigs = []
    today = dt.date.today()

    # Vorstellungen im Casinotheater Winterthur, jede einzeln
    url = CASINO + "bundesordner/"
    page = fetch(url)
    events = ld_events(page)
    if not events:
        raise SourceError("keine Events auf " + url)
    seen = set()
    for e in events:
        start = e.get("startDate", "")
        d = start[:10]
        if d < today.isoformat() or start in seen:
            continue
        seen.add(start)
        time = start[11:16]
        gigs.append({"date": d, "place": "Winterthur", "venue": f"Casinotheater · {time} Uhr" if time else "Casinotheater", "url": url})

    # Tournee: Spielorte stehen nur im Text («MI 27. JAN» / «Stadttheater Schaffhausen:»)
    url = CASINO + "bundesordner-on-tour/"
    page = fetch(url)
    events = ld_events(page)
    if not events:
        raise SourceError("keine Events auf " + url)
    lines = [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", re.sub(r"<script.*?</script>", "", page, flags=re.S))).split("\n") if l.strip()]
    places = {}
    for i, line in enumerate(lines[:-1]):
        m = re.fullmatch(r"[A-Z]{2}\s+(\d{1,2})\.\s*([A-ZÄÖÜa-zäöü]{3})\w*\.?", line)
        if m and lines[i + 1].endswith(":"):
            month = MONTHS_SHORT.get(m.group(2).lower())
            if month:
                places[(month, int(m.group(1)))] = lines[i + 1].rstrip(":").strip()
    for e in events:
        d = dt.date.fromisoformat(e["startDate"][:10])
        if d < today:
            continue
        where = places.get((d.month, d.day), "")
        gigs.append({"date": d.isoformat(), "place": where or "Tournee", "venue": "Bundesordner – On Tour", "url": url})
    return gigs


def src_jazzselection():
    """jazzselection.ch: Agenda pro Jahr (agenda-2026, agenda-2027 …), nur Termine mit Pascal Dussex."""
    gigs, found_page = [], False
    year = dt.date.today().year
    for y in (year, year + 1):
        url = f"https://www.jazzselection.ch/agenda-{y}/"
        try:
            page = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        found_page = True
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            if "dussex" not in tr.lower():
                continue
            cells = [text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", cells[0] if cells else "")
            if not m or len(cells) < 3:
                continue
            what = re.split(r"[.,]?\s*JazzSelection\b", cells[2])[0].strip(" .,")
            what = re.sub(r"\s+([.,])", r"\1", what)
            gigs.append({
                "date": dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat(),
                "place": what or "Jazz-Selection",
                "venue": f"{cells[1]} Uhr · feat. Pascal Dussex" if cells[1] else "feat. Pascal Dussex",
                "url": url,
            })
    if not found_page:
        raise SourceError("keine Agenda-Seite gefunden")
    return gigs


def src_joub():
    """joub.squarespace.com: Squarespace-Eventliste als JSON, nur Konzerte mit Pascal Dussex."""
    from zoneinfo import ZoneInfo
    base = "https://joub.squarespace.com"
    data = json.loads(fetch(base + "/concerts?format=json"))
    if "upcoming" not in data:
        raise SourceError("unerwartetes Format")
    gigs = []
    for e in data["upcoming"]:
        blob = " ".join(str(e.get(k) or "") for k in ("title", "body", "excerpt")).lower()
        if "dussex" not in blob:
            continue
        start = dt.datetime.fromtimestamp(e["startDate"] / 1000, ZoneInfo("Europe/Zurich"))
        loc = e.get("location") or {}
        town = (loc.get("addressLine2") or "").split(",")[0].strip()
        town = re.sub(r"^\d{4}\s+", "", town)
        gigs.append({
            "date": start.date().isoformat(),
            "place": town or loc.get("addressTitle", "").strip() or "JOUB",
            "venue": " · ".join(x for x in [loc.get("addressTitle", "").strip(), html.unescape(e.get("title", ""))] if x),
            "url": base + e.get("fullUrl", "/concerts"),
        })
    return gigs


def from_page(url, parser):
    return lambda: parser(fetch(url))


# Band/Projekt -> Funktion, die die Termine liefert
SOURCES = {
    "Soultrain": from_page("https://www.dussexsoultrain.ch/kalender", parse_musikerseiten),
    "Les trois Suisses": from_page("https://www.lestroissuisses.ch/tourdaten", parse_squarespace_text),
    "True Blue": from_page("https://www.trueblue-jazz.com/konzerte", parse_musikerseiten),
    "Bundesordner": src_bundesordner,
    "Jazz-Selection": src_jazzselection,
    "JOUB": src_joub,
}


def upcoming(g, today):
    return (g.get("date_end") or g["date"]) >= today


def main():
    today = dt.date.today().isoformat()
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        old = []

    result, failures = [], []
    for band, source in SOURCES.items():
        previous = [g for g in old if g["band"] == band and upcoming(g, today)]
        try:
            gigs = [g for g in source() if upcoming(g, today)]
            if not gigs and previous:
                raise SourceError("keine Termine mehr gefunden (vorher %d)" % len(previous))
            for g in gigs:
                g["band"] = band
            result += gigs
            print(f"{band}: {len(gigs)} Termine")
        except Exception as e:  # Netzwerk, Parser, alles: alte Daten behalten
            failures.append(band)
            result += previous
            print(f"FEHLER {band}: {e} – behalte {len(previous)} bisherige Termine", file=sys.stderr)

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
