def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Text search via DuckDuckGo."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []


def search_news(query: str, max_results: int = 8) -> list[dict]:
    """News search via DuckDuckGo."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            return list(ddgs.news(query, max_results=max_results))
    except Exception:
        return []
