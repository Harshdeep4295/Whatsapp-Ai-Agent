import re
import hashlib
import feedparser
from bot.llm import get_client
from bot.web_search import search_news

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

def _fetch_all_headlines() -> list[tuple[str, str, str]]:
    """Returns list of (title, link, snippet) from all feeds."""
    items = []
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                raw = entry.get("summary", "") or entry.get("description", "")
                snippet = re.sub(r"<[^>]+>", "", raw).strip()[:200]
                if title:
                    items.append((title, link, snippet))
        except Exception:
            continue
    return items

def _search_fresh_news(exam: str) -> list[tuple[str, str, str]]:
    """Fallback: DuckDuckGo search for latest Haryana news."""
    results = search_news("Haryana India current affairs today", max_results=8)
    return [
        (r.get("title", ""), r.get("url", ""), r.get("body", "")[:200])
        for r in results if r.get("title")
    ]

def get_current_affairs(exam: str = "General", last_hash: str = None, seen_keys: list = None) -> tuple[str, str, list]:
    """
    Returns (summary_text, content_hash, seen_keys).
    If last_hash is provided, tries to fetch content different from last time.
    seen_keys is a rolling list of story keys already sent to this user.
    """
    headlines = _fetch_all_headlines()

    if not headlines:
        headlines = _search_fresh_news(exam)

    if not headlines:
        return "Could not fetch news right now. Try again in a few minutes.", "", seen_keys or []

    # If we have a last_hash, try to surface fresh content at the top
    if last_hash:
        fresh = _search_fresh_news(exam)
        if fresh:
            seen_titles = {t.lower() for t, _, _s in headlines[:8]}
            headlines = [(t, l, s) for t, l, s in fresh if t.lower() not in seen_titles] + headlines

    # Filter stories already sent to this user
    already_sent = set(seen_keys or [])
    seen_in_batch, unique = set(), []
    for title, link, snippet in headlines:
        key = title.lower()[:50]
        if key not in seen_in_batch and key not in already_sent:
            seen_in_batch.add(key)
            unique.append((title, snippet))
        if len(unique) >= 10:
            break

    # If all stories were already sent, fall back to best available (don't skip entirely)
    if not unique:
        unique = [(t, s) for t, _, s in headlines[:5]]

    # Build context lines with snippet where available
    story_lines = [f"- {t}: {s}" if s else f"- {t}" for t, s in unique]
    stories_text = "\n".join(story_lines)
    content_hash = hashlib.md5(stories_text.encode()).hexdigest()

    # Same as before even after searching — nothing new available
    if content_hash == last_hash:
        return None, last_hash, seen_keys or []

    client = get_client()
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content":
            "You are preparing current affairs notes for a Haryana Civil Services (HCS/HPSC) Prelims student.\n\n"
            "From these news stories, pick the 5 most relevant items for HCS exam (prioritise Haryana news, "
            "then national polity/economy/science/environment/government schemes).\n\n"
            "For each item, write ONE bullet: *actual fact* (who/what/where/key number) — then 1 line on HCS relevance.\n\n"
            "Rules: State real facts only. No study tips. No 'this relates to chapter X'.\n\n"
            f"Stories:\n{stories_text}"
        }],
        max_tokens=500,
    )
    summary = "*HCS Current Affairs*\n\n" + r.choices[0].message.content

    # Return updated seen keys (rolling window of last 30)
    new_seen = list(already_sent) + list(seen_in_batch)
    return summary, content_hash, new_seen[-30:]
