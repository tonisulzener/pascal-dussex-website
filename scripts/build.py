#!/usr/bin/env python3
"""Erzeugt index.html aus content/site.json + templates/index.html.j2
und verkleinert zu grosse Fotos in img/ (z.B. Uploads aus dem Admin-Editor).

Benötigt: pip install jinja2 pillow
"""
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
                im.save(path, optimize=True)
            else:
                im.convert("RGB").save(path, quality=80, optimize=True, progressive=True)
        print(f"Bild optimiert: {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


def main():
    content = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
        undefined=ChainableUndefined,
        keep_trailing_newline=True,
    )
    env.filters.update(domain=domain, tel=tel, nl2br=nl2br)
    env.globals["pos"] = pos
    html = env.get_template("index.html.j2").render(**content)

    missing = [src for src in re.findall(r'<img src="([^"]+)"', html) if not (ROOT / src).exists()]
    if missing:
        sys.exit("Bilder nicht gefunden: " + ", ".join(missing))

    (ROOT / "index.html").write_text(html, encoding="utf-8")
    print("index.html erzeugt")
    optimize_images()


if __name__ == "__main__":
    main()
