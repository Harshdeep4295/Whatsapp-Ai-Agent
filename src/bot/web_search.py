def _tavily_to_ddg(results: list[dict]) -> list[dict]:
    """Normalize Tavily result fields to match DuckDuckGo field names."""
    return [{"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("content", "")} for r in results]


def search_web(query: str, max_results: int = 5) -> list[dict]:
    from config import TAVILY_API_KEY
    if TAVILY_API_KEY:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=TAVILY_API_KEY)
            results = client.search(query, max_results=max_results).get("results", [])
            return _tavily_to_ddg(results)
        except Exception:
            pass  # fall through to DuckDuckGo
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []


def search_news(query: str, max_results: int = 8) -> list[dict]:
    from config import TAVILY_API_KEY
    if TAVILY_API_KEY:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=TAVILY_API_KEY)
            results = client.search(query, topic="news", max_results=max_results).get("results", [])
            return _tavily_to_ddg(results)
        except Exception:
            pass
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            return list(ddgs.news(query, max_results=max_results))
    except Exception:
        return []
