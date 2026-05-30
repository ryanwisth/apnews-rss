# apnews-rss

Unofficial RSS + Atom feeds scraped from apnews.com, refreshed hourly by GitHub Actions, served by GitHub Pages.

## Feeds (once Pages is enabled)

After the first successful run, your feeds are at:

- Top: `https://ryanwisth.github.io/apnews-rss/ap-top.xml`
- U.S.: `https://ryanwisth.github.io/apnews-rss/ap-us.xml`
- World: `https://ryanwisth.github.io/apnews-rss/ap-world.xml`
- Politics: `https://ryanwisth.github.io/apnews-rss/ap-politics.xml`
- Business: `https://ryanwisth.github.io/apnews-rss/ap-business.xml`
- Tech: `https://ryanwisth.github.io/apnews-rss/ap-technology.xml`
- Science: `https://ryanwisth.github.io/apnews-rss/ap-science.xml`
- Health: `https://ryanwisth.github.io/apnews-rss/ap-health.xml`
- Sports: `https://ryanwisth.github.io/apnews-rss/ap-sports.xml`
- Entertainment: `https://ryanwisth.github.io/apnews-rss/ap-entertainment.xml`

Atom variants: replace `.xml` with `.atom`.

A landing page lives at `https://ryanwisth.github.io/apnews-rss/`.

## One-time setup

1. Create a new public repository on GitHub named `apnews-rss` under your user `ryanwisth` (Settings → New repository, public, no README).
2. Push these files to the repo's `main` branch (drag-and-drop in the web UI works, or push from local).
3. On the repo page: Settings → Pages → "Build and deployment" → "Source: GitHub Actions". Save.
4. The first scheduled run will fire within an hour. To trigger immediately: Actions tab → "Scrape AP News and publish feeds" → "Run workflow".
5. After ~1–2 minutes the feeds are live at the URLs above. Subscribe in KOReader's News.

## Notes

- Scraper is in `scraper.py`. Edit `SECTIONS` to add or remove categories.
- It tries `__NEXT_DATA__` JSON parsing first (the structured server-rendered payload), falls back to anchor scraping if the JSON layout drifts.
- If AP changes their HTML enough to break both paths, the workflow fails loud (exit 2) so you'll see it in Actions.
- Feeds cap at 30 items per section.

## Customizing

- Add sections: extend the `SECTIONS` dict at the top of `scraper.py` with the apnews.com URL and a display name.
- Change frequency: edit the `cron` line in `.github/workflows/scrape.yml`. Hourly (`17 * * * *`) is the default; every 30 minutes would be `*/30 * * * *`.
- The bot uses `ap-rss-bot@users.noreply.github.com` for commits to keep your contributions graph clean.
