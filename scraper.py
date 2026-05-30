#!/usr/bin/env python3
"""
AP News scraper -> RSS 2.0 + Atom 1.0

Fetches apnews.com section pages, extracts article cards, emits feed files
that GitHub Pages serves at stable URLs.

Designed to be tolerant of layout drift: tries structured __NEXT_DATA__ JSON
first, falls back to HTML card parsing.
"""

import datetime as dt
import json
import re
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# Sections to scrape. Each generates ap-<key>.xml (RSS) and ap-<key>.atom (Atom).
# Edit this dict to add/remove sections.
SECTIONS = {
    "top": ("https://apnews.com/hub/ap-top-news", "AP Top News"),
    "us": ("https://apnews.com/us-news", "AP U.S. News"),
    "world": ("https://apnews.com/world-news", "AP World News"),
    "politics": ("https://apnews.com/politics", "AP Politics"),
    "business": ("https://apnews.com/business", "AP Business"),
    "technology": ("https://apnews.com/technology", "AP Technology"),
    "science": ("https://apnews.com/science", "AP Science"),
    "health": ("https://apnews.com/health", "AP Health"),
    "sports": ("https://apnews.com/sports", "AP Sports"),
    "entertainment": ("https://apnews.com/entertainment", "AP Entertainment"),
}

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = httpx.Timeout(20.0)
MAX_ITEMS = 30


def fetch(url: str) -> str:
    """Fetch a URL with a desktop UA. Raises on non-2xx."""
    with httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": UA, "Accept": "text/html,*/*"},
    ) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def parse_next_data(html: str):
    """Try to find Next.js __NEXT_DATA__ JSON and extract article entries.

    Returns a list of dicts: {title, url, published, summary}.
    Returns [] if not present or unparseable.
    """
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return []

    items = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            # Heuristic: a card-like node has at least a title/href and maybe a date.
            link = node.get("href") or node.get("url") or node.get("link")
            title = (
                node.get("title")
                or node.get("headline")
                or node.get("name")
                or node.get("text")
            )
            if (
                isinstance(link, str)
                and isinstance(title, str)
                and link.startswith("/article/")
                and len(title) > 10
            ):
                full = "https://apnews.com" + link
                if full not in seen:
                    seen.add(full)
                    items.append(
                        {
                            "title": title.strip(),
                            "url": full,
                            "published": (
                                node.get("publishedDate")
                                or node.get("published")
                                or node.get("date")
                            ),
                            "summary": node.get("description") or node.get("flyTitle") or "",
                        }
                    )
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return items


def parse_cards(html: str):
    """Parse visible article cards from the HTML.

    AP uses URLs of the form `https://apnews.com/article/<slug>-<32-hex>` (and the
    occasional relative `/article/<slug>`). We grab both forms.
    """
    soup = BeautifulSoup(html, "lxml")
    items = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Normalize to full URL.
        if href.startswith("/article/"):
            full = "https://apnews.com" + href
        elif href.startswith("https://apnews.com/article/"):
            full = href
        else:
            continue
        # Drop query strings and fragments so the same article doesn't appear twice
        # with different tracking params.
        full = full.split("?")[0].split("#")[0]
        if full in seen:
            continue
        # Headline is the link's text, often wrapped in an h-tag inside.
        title = (a.get_text(" ", strip=True) or "").strip()
        if len(title) < 10:
            h = a.find(["h1", "h2", "h3", "h4"])
            if h:
                title = h.get_text(" ", strip=True)
        if len(title) < 10:
            continue
        seen.add(full)
        items.append({"title": title, "url": full, "published": None, "summary": ""})
    return items


def parse_published(s):
    if not s:
        return None
    # Try ISO 8601 with or without Z.
    try:
        if s.endswith("Z"):
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.datetime.fromisoformat(s)
    except ValueError:
        pass
    # Try epoch ms.
    try:
        if isinstance(s, (int, float)) or (isinstance(s, str) and s.isdigit()):
            ms = int(s)
            if ms > 10_000_000_000:  # ms
                return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
            return dt.datetime.fromtimestamp(ms, tz=dt.timezone.utc)
    except Exception:
        pass
    return None


def build_feed(section_key: str, section_url: str, section_title: str, items, out_dir: Path):
    fg = FeedGenerator()
    fg.id(section_url)
    fg.title(f"{section_title} (unofficial)")
    fg.link(href=section_url, rel="alternate")
    fg.link(
        href=f"https://ryanwisth.github.io/apnews-rss/ap-{section_key}.xml",
        rel="self",
    )
    fg.description(f"Unofficial RSS feed of {section_title} from apnews.com")
    fg.language("en")
    fg.generator("ap-rss scraper")
    fg.updated(dt.datetime.now(dt.timezone.utc))
    fg.author({"name": "AP News (scraped, unofficial)"})

    now = dt.datetime.now(dt.timezone.utc)
    items = items[:MAX_ITEMS]
    for i, it in enumerate(items):
        fe = fg.add_entry()
        fe.id(it["url"])
        fe.title(it["title"])
        fe.link(href=it["url"])
        # Use real published date if available; otherwise stagger by index so
        # readers don't show all items at the exact same instant.
        pub = parse_published(it.get("published")) or (now - dt.timedelta(minutes=i))
        fe.published(pub)
        fe.updated(pub)
        if it.get("summary"):
            fe.summary(it["summary"])

    rss_path = out_dir / f"ap-{section_key}.xml"
    atom_path = out_dir / f"ap-{section_key}.atom"
    fg.rss_file(str(rss_path), pretty=True)
    fg.atom_file(str(atom_path), pretty=True)
    return rss_path, atom_path


def write_index(out_dir: Path, results):
    """Tiny landing page listing every feed URL."""
    items = "\n".join(
        f'  <li><strong>{title}</strong> &mdash; '
        f'<a href="ap-{key}.xml">RSS</a> / '
        f'<a href="ap-{key}.atom">Atom</a> ({count} items)</li>'
        for key, title, count in results
    )
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>AP News feeds (unofficial)</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
ul {{ list-style: none; padding-left: 0; }}
li {{ margin-bottom: 0.4rem; }}
small {{ color: #666; }}
</style>
<h1>AP News feeds (unofficial)</h1>
<p>Hourly-updated RSS and Atom feeds scraped from apnews.com.</p>
<ul>
{items}
</ul>
<p><small>Last build: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}</small></p>
"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def main():
    out_dir = Path(__file__).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    any_built = False

    for key, (url, title) in SECTIONS.items():
        try:
            print(f"[{key}] fetching {url}", flush=True)
            html = fetch(url)
        except Exception as e:
            print(f"[{key}] fetch failed: {e}", file=sys.stderr)
            results.append((key, title, 0))
            continue

        items = parse_next_data(html)
        if not items:
            print(f"[{key}] __NEXT_DATA__ yielded 0 items, falling back to card scrape")
            items = parse_cards(html)
        # Filter out non-article entries (assets, section landing pages, etc.)
        items = [it for it in items if "/article/" in it["url"]]
        # De-duplicate across items list (in case both parsers ran)
        seen_urls = set()
        deduped = []
        for it in items:
            if it["url"] in seen_urls:
                continue
            seen_urls.add(it["url"])
            deduped.append(it)
        items = deduped
        print(f"[{key}] {len(items)} items", flush=True)

        if items:
            build_feed(key, url, title, items, out_dir)
            any_built = True
        results.append((key, title, len(items)))

    write_index(out_dir, results)

    if not any_built:
        print("No feeds had any items. Failing build so the missing-data is visible.",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
