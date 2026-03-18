import hashlib
import feedparser
from bot.llm import get_client

# Multiple feed pools — rotated to get fresh content each time
FEEDS = [
    # Haryana-specific sources (prioritized for HCS prep)
    "https://www.tribuneindia.com/rss/haryana.xml",
    "https://www.hindustantimes.com/feeds/rss/cities/chandigarh/rssfeed.xml",
    # National current affairs sources
    "https://www.clearias.com/feed/",
    "https://currentaffairs.gktoday.in/feed",
    "https://www.jagranjosh.com/current-affairs/rss-feed",
    "https://www.thehindu.com/news/national/feeder/default.rss",
    "https://indianexpress.com/feed/",
    "https://feeds.feedburner.com/ndtvnews-india-news",
    "https://www.livemint.com/rss/news",
    "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
]

def _fetch_all_headlines() -> list[tuple[str, str]]:
    """Returns list of (title, link) from all feeds."""
    items = []
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                if title:
                    items.append((title, link))
        except Exception:
            continue
    return items

def _search_fresh_news(exam: str) -> list[tuple[str, str]]:
    """Fallback: DuckDuckGo search for latest news."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.news(f"{exam} current affairs today", max_results=8))
        return [(r.get("title", ""), r.get("url", "")) for r in results if r.get("title")]
    except Exception:
        return []

def get_current_affairs(exam: str = "General", last_hash: str = None) -> tuple[str, str]:
    """
    Returns (summary_text, content_hash).
    If last_hash is provided, tries to fetch content different from last time.
    """
    headlines = _fetch_all_headlines()

    if not headlines:
        headlines = _search_fresh_news(exam)

    if not headlines:
        return "Could not fetch news right now. Try again in a few minutes.", ""

    # If we have a last_hash, filter out titles that were likely in the previous batch
    # by trying more feeds or searching for fresh content
    if last_hash:
        fresh = _search_fresh_news(exam)
        if fresh:
            # Merge fresh results at the top
            seen_titles = {t.lower() for t, _ in headlines[:8]}
            new_items = [(t, l) for t, l in fresh if t.lower() not in seen_titles]
            headlines = new_items + headlines

    # Take top 10 unique headlines
    seen, unique = set(), []
    for title, link in headlines:
        key = title.lower()[:50]
        if key not in seen:
            seen.add(key)
            unique.append((title, link))
        if len(unique) >= 10:
            break

    headline_text = "\n".join(f"- {t}" for t, _ in unique)
    content_hash = hashlib.md5(headline_text.encode()).hexdigest()

    # Same as before even after searching — nothing new available
    if content_hash == last_hash:
        return None, last_hash

    client = get_client()
    r = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content":
            f"Summarize these headlines for a {exam} exam student. "
            f"Give 5 bullet points, focus on exam-relevant topics:\n{headline_text}"
        }],
        max_tokens=300,
    )
    summary = "*Latest Current Affairs*\n\n" + r.choices[0].message.content
    return summary, content_hash
