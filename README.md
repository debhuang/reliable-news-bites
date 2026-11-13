# Reliable News Bites

A free daily news website. Every morning a GitHub Action reads RSS feeds from trusted publishers, groups the stories by topic, removes duplicates and publishes them with GitHub Pages. It needs no API keys and costs $0.

```
GitHub Actions (daily cron) → scripts/fetch_news.py → commits docs/news.json → GitHub Pages
```

The site shows only the headline, a short summary and a link to the original article. It never scrapes full articles.

## Files

| Path | What it does |
| --- | --- |
| `feeds.json` | Your categories and RSS feeds. Edit this to change what you read. |
| `scripts/fetch_news.py` | Downloads the feeds, cleans and dedupes them, writes `docs/news.json`. |
| `docs/` | The website (plain HTML/CSS/JS, no build step). |
| `.github/workflows/update-news.yml` | Runs the script every day at 12:00 UTC and commits the result. |

## One-time setup

1. Make the repository **public**. GitHub Pages and Actions minutes are free for public repos.
2. Merge this code into `main`.
3. **Settings → Pages**: set Source to *Deploy from a branch*, then pick branch `main` and folder `/docs`.
4. **Actions → Update news → Run workflow** to fetch the first batch now instead of waiting for tomorrow.

Your site will be at `https://<your-username>.github.io/reliable-news-bites/`.

If the workflow fails to push, go to **Settings → Actions → General → Workflow permissions** and choose *Read and write permissions*.

## Customizing

- **Add a topic:** add a category to `feeds.json`. Any topic works with a Google News search feed:
  `https://news.google.com/rss/search?q=YOUR+TOPIC+when:2d&hl=en-US&gl=US&ceid=US:en`
- **Change the time:** edit the `cron` line in the workflow. It's in UTC: `0 12 * * *` is 7 AM New York in winter and 8 AM in summer.
- **Tune the limits:** `MAX_AGE_HOURS`, `MAX_PER_CATEGORY` and `MAX_PER_SOURCE` are at the top of `scripts/fetch_news.py`.

## Run it locally

```bash
pip install -r requirements.txt
python scripts/fetch_news.py
python -m http.server -d docs 8000   # open http://localhost:8000
```

## Things to know

- Scheduled runs can start 15+ minutes late when GitHub is busy.
- GitHub turns off scheduled workflows after 60 days with no repo activity. The bot's daily commit keeps the repo active.
- If a feed is down, the site still updates with the others and shows which source it couldn't reach. If every feed fails, yesterday's news stays up.
