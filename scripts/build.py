#!/usr/bin/env python3
"""Erzeugt index.html, impressum.html und datenschutz.html aus content/site.json + templates/
verkleinert zu grosse Fotos in img/ (z.B. Uploads aus dem Admin-Editor)
und entfernt Metadaten wie GPS-Standort aus allen Bildern.

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


# Metadaten-Segmente, die entfernt werden: EXIF/XMP (APP1, enthält GPS, Kamera, Datum),
# IPTC (APP13) und Kommentare. Farbprofile (APP2/ICC) bleiben erhalten.
JPEG_DROP = {0xE1, 0xED, 0xFE}
PNG_DROP = {b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"tIME"}


def strip_jpeg(data):
    """Entfernt Metadaten verlustfrei aus einer JPEG-Datei (Bilddaten bleiben unverändert)."""
    if data[:2] != b"\xff\xd8":
        return data
    out, i = bytearray(data[:2]), 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        if marker == 0xDA:  # Start of Scan: ab hier nur noch Bilddaten
            break
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker not in JPEG_DROP:
            out += data[i:i + 2 + length]
        i += 2 + length
    return bytes(out + data[i:])


def strip_png(data):
    """Entfernt Text-, Zeit- und EXIF-Blöcke aus einer PNG-Datei."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return data
    out, i = bytearray(data[:8]), 8
    while i + 8 <= len(data):
        length = int.from_bytes(data[i:i + 4], "big")
        kind = data[i + 4:i + 8]
        chunk = data[i:i + 12 + length]
        if kind not in PNG_DROP:
            out += chunk
        i += 12 + length
    return bytes(out)


def strip_metadata(folders=("img", "assets")):
    """Entfernt GPS-Standort, Kameradaten usw. aus allen Bildern. Bilder mit Drehung im EXIF
    werden vorher richtig herum gespeichert, damit sie nach dem Entfernen nicht kippen."""
    from PIL import Image, ImageOps
    for folder in folders:
        for path in sorted((ROOT / folder).glob("*")):
            suffix = path.suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png"}:
                continue
            data = path.read_bytes()
            if suffix in {".jpg", ".jpeg"}:
                with Image.open(path) as im:
                    turned = im.getexif().get(0x0112, 1) not in (1, None)
                    if turned:
                        ImageOps.exif_transpose(im).convert("RGB").save(path, quality=85, optimize=True, progressive=True)
                        data = path.read_bytes()
                clean = strip_jpeg(data)
            else:
                clean = strip_png(data)
            if clean != data:
                path.write_bytes(clean)
                print(f"Metadaten entfernt: {path.relative_to(ROOT)}")


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
    strip_metadata()


if __name__ == "__main__":
    main()
