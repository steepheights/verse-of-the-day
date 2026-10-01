"""Verse of the day: take a verse from the Berean Standard Bible, draw a card, post it to Instagram.

Commands:
  python post.py check                 confirm every reference in verses.csv exists in the Bible file
  python post.py render  [--date D]    write posts/D.jpg and posts/D.json for that day's verse
  python post.py publish [--date D]    post posts/D.jpg to Instagram (needs IMAGE_BASE_URL)

Environment variables (publish only):
  IG_ACCESS_TOKEN    system user token from Meta Business Settings (Instagram API with Facebook Login)
  IG_USER_ID         the Instagram professional account's ID; if unset, publish lists the IDs the token can reach
  IMAGE_BASE_URL     public URL of the repo root that holds posts/, no trailing slash
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

IG_API = "https://graph.facebook.com/v23.0"
REFERENCE = re.compile(r"^(?P<book>.+?) (?P<chapter>\d+):(?P<first>\d+)(?:-(?P<last>\d+))?$")


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        fail(f"environment variable {name} is not set")
    return value


def today():
    return dt.datetime.now(ZoneInfo(CONFIG["timezone"])).date()


def parse_date(value):
    return dt.date.fromisoformat(value) if value else today()


# ---------- verse selection and lookup ----------

@cache
def bible():
    """Map 'John 3:16' -> verse text, from the tab-separated BSB file."""
    verses = {}
    with open(ROOT / CONFIG["bible_file"], encoding="utf-8-sig") as f:
        for line in f:
            ref, sep, text = line.rstrip("\r\n").partition("\t")
            if sep and REFERENCE.match(ref):
                verses[ref] = text.strip()
    if not verses:
        fail(f"no verses found in {CONFIG['bible_file']}")
    return verses


def load_list():
    with open(ROOT / "verses.csv", newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["reference"].strip()]
    if not rows:
        fail("verses.csv has no rows")
    return rows


def entry_for(day):
    rows = load_list()
    start = dt.date.fromisoformat(CONFIG["start_date"])
    return rows[(day - start).days % len(rows)]


def lookup(entry):
    reference = entry["reference"].strip()
    m = REFERENCE.match(reference)
    if not m:
        fail(f"cannot read reference '{reference}' (expected e.g. 'John 3:16' or 'Proverbs 3:5-6')")
    book, chapter, first = m["book"], m["chapter"], int(m["first"])
    last = int(m["last"] or first)
    parts = []
    for verse in range(first, last + 1):
        key = f"{book} {chapter}:{verse}"
        if key not in bible():
            fail(f"'{key}' is not in {CONFIG['bible_file']}")
        parts.append(bible()[key])
    text = " ".join(parts)

    heading = (entry.get("heading") or "").strip()
    if heading:
        if not text.startswith(heading):
            fail(f"{reference}: text does not start with the heading '{heading}'")
        text = text[len(heading):].strip()
    return {"reference": reference, "text": re.sub(r"\s+", " ", text)}


# ---------- image ----------

def load_font(path, size):
    for candidate in (ROOT / path, Path(CONFIG["image"]["fallback_font"])):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def wrap(draw, text, font, max_width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render_card(verse, out_path):
    cfg = CONFIG["image"]
    w, h = cfg["width"], cfg["height"]
    top, bottom = hex_rgb(cfg["gradient_top"]), hex_rgb(cfg["gradient_bottom"])

    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        draw.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))

    text_colour = hex_rgb(cfg["text_colour"])
    accent = hex_rgb(cfg["accent_colour"])
    margin = 110
    max_width = w - 2 * margin
    box_height = h - 520  # leaves room for the rule, reference and handle

    for size in range(68, 29, -2):
        font = load_font(cfg["verse_font"], size)
        lines = wrap(draw, verse["text"], font, max_width)
        line_height = round(size * 1.45)
        if line_height * len(lines) <= box_height:
            break

    ref_font = load_font(cfg["reference_font"], 40)
    handle_font = load_font(cfg["reference_font"], 30)
    block = line_height * len(lines) + 60 + 4 + 50 + 44
    y = (h - block) // 2 - 30

    for line in lines:
        draw.text((w / 2, y), line, font=font, fill=text_colour, anchor="ma")
        y += line_height

    y += 60
    draw.line([(w / 2 - 50, y), (w / 2 + 50, y)], fill=accent, width=3)
    y += 50
    draw.text((w / 2, y), labelled(verse), font=ref_font, fill=accent, anchor="ma")
    draw.text((w / 2, h - 90), CONFIG["handle"], font=handle_font, fill=accent, anchor="ma")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92)


def labelled(verse):
    """'John 3:16', or 'John 3:16 (BSB)' when translation_label is set."""
    label = CONFIG.get("translation_label", "").strip()
    return f"{verse['reference']} ({label})" if label else verse["reference"]


def caption_for(verse):
    return "\n\n".join([
        verse["text"],
        labelled(verse),
        CONFIG["attribution"],
        " ".join(CONFIG["hashtags"]),
    ])


# ---------- Instagram ----------

def ig(method, path, **params):
    params["access_token"] = env("IG_ACCESS_TOKEN")
    resp = requests.request(method, f"{IG_API}/{path}", params=params, timeout=60)
    if not resp.ok:
        fail(f"Instagram API {method} {path} failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json()


def ig_user_id():
    user_id = os.environ.get("IG_USER_ID", "").strip()
    if user_id:
        return user_id
    pages = ig("GET", "me/accounts", fields="name,instagram_business_account{id,username}").get("data", [])
    found = [f"@{p['instagram_business_account']['username']}: {p['instagram_business_account']['id']} (Page: {p['name']})"
             for p in pages if p.get("instagram_business_account")]
    fail("IG_USER_ID is not set. Instagram accounts this token can reach:\n  "
         + ("\n  ".join(found) or "none. Check the system user has the Page and the Instagram account assigned."))


def publish(day):
    image = POSTS / f"{day}.jpg"
    meta_path = POSTS / f"{day}.json"
    marker = POSTS / f"{day}.posted"
    if marker.exists():
        print(f"{day} is already posted; nothing to do.")
        return
    if not image.exists() or not meta_path.exists():
        fail(f"run 'render' first: {image.name} or {meta_path.name} is missing")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    user_id = ig_user_id()
    image_url = f"{env('IMAGE_BASE_URL')}/posts/{image.name}"
    container = ig("POST", f"{user_id}/media", image_url=image_url,
                   caption=meta["caption"], alt_text=meta["alt_text"])["id"]

    for _ in range(24):
        status = ig("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            fail(f"Instagram could not process the image (status {status}). URL: {image_url}")
        time.sleep(5)
    else:
        fail("Instagram took too long to process the image")

    media_id = ig("POST", f"{user_id}/media_publish", creation_id=container)["id"]
    marker.write_text(json.dumps({"media_id": media_id, "posted_at": dt.datetime.now(dt.timezone.utc).isoformat()}),
                      encoding="utf-8")
    print(f"Posted {meta['reference']} for {day} (media id {media_id}).")


# ---------- commands ----------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["check", "render", "publish"])
    parser.add_argument("--date", help="YYYY-MM-DD (default: today in the configured time zone)")
    args = parser.parse_args()

    if args.command == "check":
        rows = load_list()
        for row in rows:
            lookup(row)
        print(f"OK: all {len(rows)} references found in {CONFIG['bible_file']} ({len(bible())} verses loaded).")
    elif args.command == "render":
        day = parse_date(args.date)
        verse = lookup(entry_for(day))
        render_card(verse, POSTS / f"{day}.jpg")
        meta = {
            "date": str(day),
            "reference": verse["reference"],
            "caption": caption_for(verse),
            "alt_text": f"{labelled(verse)}: {verse['text']}",
        }
        (POSTS / f"{day}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Rendered {verse['reference']} for {day}.")
    elif args.command == "publish":
        publish(parse_date(args.date))


if __name__ == "__main__":
    main()
