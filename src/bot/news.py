import feedparser
from bot.llm import get_client

FEEDS = [
    "https://www.clearias.com/feed/",
    "https://currentaffairs.gktoday.in/feed",
    "https://www.jagranjosh.com/current-affairs/rss-feed",
]

def get_current_affairs(exam: str = "HCS") -> str:
    items = []
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:4]:
                items.append(entry.title)
        except Exception:
            continue
        if len(items) >= 8:
            break

    if not items:
        return "Could not fetch news right now. Try again in a few minutes."

    headlines = "\n".join(f"- {h}" for h in items[:8])
    client = get_client()
    r = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content":
            f"Summarize for a {exam} exam student. "
            f"5 bullet points, exam-relevant focus:\n{headlines}"
        }],
        max_tokens=300,
    )
    return "*Today's Current Affairs*\n\n" + r.choices[0].message.content
