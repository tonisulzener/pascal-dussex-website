#!/usr/bin/env python3
"""Erzeugt index.html, impressum.html und datenschutz.html aus content/site.json + templates/
und verkleinert zu grosse Fotos in img/ (z.B. Uploads aus dem Admin-Editor).

Benötigt: pip install jinja2 pillow
"""
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, ChainableUndefined
from markupsafe import Markup, escape

ROOT = Path(__file__).resolve().parent.parent
MAX_SIDE = 1600          # längste Bildseite in Pixel
MAX_BYTES = 700 * 1024   # grössere Dateien werden neu komprimiert


def domain(url):
    host = urlparse(url).netloc or url
    return host.removeprefix("www.").rstrip("/")


def slug(url):
    """https://www.dussexsoultrain.ch/ -> «dussexsoultrain» (Anker und CSS-Klasse)."""
    return re.sub(r"[^a-z0-9]+", "-", domain(url).lower().rsplit(".", 1)[0]).strip("-")


def nameslug(name):
    """«Mario & Friends» -> «mario-und-friends» (Anker)."""
    name = name.lower().replace("&", "und")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        name = name.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


# Buchstabenfarben wie im Soultrain-Flyer (CSS-Klassen .st-1 … .st-9)
def soultrain(name):
    """Färbt den Bandnamen mit «Soultrain» Buchstabe für Buchstabe."""
    m = re.search(r"soultrain", name, re.I)
    if not m:
        return escape(name)
    def paint(text):
        out, i = [], 0
        for c in text:
            if c.isspace():
                out.append(c)
            else:
                i += 1
                out.append(f'<span class="st-{(i - 1) % 9 + 1}">{escape(c)}</span>')
        return "".join(out)
    # Vor- und Nachsatz (z.B. «Dussex' ») ebenfalls bunt, «Soultrain» exakt wie im Flyer
    return Markup(paint(name[:m.start()]) + paint(m.group(0)) + paint(name[m.end():]))


def tel(number):
    digits = re.sub(r"[^\d+]", "", number)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("0"):
        digits = "+41" + digits[1:]
    return "tel:" + digits


def nl2br(text):
    return Markup("<br>".join(escape(line) for line in str(text).splitlines()))


def pos(value):
    """Bildausschnitt, z.B. «center 30%» -> style-Attribut. Ungültiges wird ignoriert."""
    value = (value or "").strip()
    if not value or not re.fullmatch(r"[a-z0-9%. -]+", value):
        return ""
    return Markup(f' style="object-position:{value}"')


def asset(path):
    """styles.css -> styles.css?v=1a2b3c4d, damit Browser nach Änderungen nicht die alte Datei zeigen."""
    digest = hashlib.md5((ROOT / path).read_bytes()).hexdigest()[:8]
    return f"{path}?v={digest}"


def optimize_images():
    try:
        from PIL import Image, ImageOps
    except ImportError:
        print("Pillow fehlt – Bilder werden nicht optimiert", file=sys.stderr)
        return
    for path in sorted((ROOT / "img").rglob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        with Image.open(path) as im:
            too_big = max(im.size) > MAX_SIDE or path.stat().st_size > MAX_BYTES
            if not too_big:
                continue
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            if path.suffix.lower() == ".png":
                # Grafiken/Flyer: auf 256 Farben reduzieren, sonst bleiben PNGs mehrere MB gross
                im = im.convert("RGBA").quantize(256, method=Image.Quantize.FASTOCTREE)
                im.save(path, optimize=True)
            else:
                im.convert("RGB").save(path, quality=80, optimize=True, progressive=True)
        print(f"Bild optimiert: {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


def relative_paths(value):
    """Der Admin-Editor speichert Bilder als «/img/…». Auf GitHub Pages liegt die Seite in einem
    Unterordner, deshalb überall relativ «img/…» verwenden."""
    if isinstance(value, dict):
        return {k: relative_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [relative_paths(v) for v in value]
    if isinstance(value, str) and value.startswith("/img/"):
        return value[1:]
    return value


def main():
    content = relative_paths(json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8")))
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
        undefined=ChainableUndefined,
        keep_trailing_newline=True,
    )
    env.filters.update(domain=domain, slug=slug, nameslug=nameslug, soultrain=soultrain, tel=tel, nl2br=nl2br)
    env.globals.update(pos=pos, asset=asset)
    year = __import__("datetime").date.today().year
    pages = {
        "index.html": ("index.html.j2", ""),
        "impressum.html": ("impressum.html.j2", "index.html"),
        "datenschutz.html": ("datenschutz.html.j2", "index.html"),
    }
    for out, (template, home) in pages.items():
        html = env.get_template(template).render(**content, home=home, year=year)
        missing = [src for src in re.findall(r'<img src="([^"]+)"', html) if not (ROOT / src).exists()]
        if missing:
            sys.exit(f"{out}: Bilder nicht gefunden: " + ", ".join(missing))
        (ROOT / out).write_text(html, encoding="utf-8")
        print(f"{out} erzeugt")
    optimize_images()


if __name__ == "__main__":
    main()
