import httpx
import uuid
import fitz
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from supabase import create_client
from bot.rag import add_to_chromadb
from config import SUPABASE_URL, SUPABASE_KEY

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

def is_cached(exam: str, content_type: str, subject: str = "") -> bool:
    res = sb.table("content_cache")\
        .select("id").eq("exam", exam)\
        .eq("content_type", content_type)\
        .execute()
    return bool(res.data)

def search_and_fetch(exam: str, content_type: str,
                     subject: str = "", year: int = None) -> str:
    if is_cached(exam, content_type, subject):
        return "loaded_from_cache"

    if content_type == "syllabus":
        query = f"{exam} exam official syllabus 2024 topics"
    elif content_type == "paper":
        yr = str(year) if year else "previous year"
        query = f"{exam} {yr} question paper {subject} filetype:pdf"
    else:
        query = f"{exam} {subject} study material"

    chunks, title, source_url = [], "", ""

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        for r in results:
            url = r.get("href", "")
            title = r.get("title", "")
            source_url = url
            if url.lower().endswith(".pdf"):
                chunks = _fetch_pdf(url)
            else:
                chunks = _fetch_webpage(url)
            if chunks:
                break
    except Exception:
        return "fetch_failed"

    if not chunks:
        return "no_content"

    chunk_ids = [str(uuid.uuid4()) for _ in chunks]
    meta = [{"exam": exam, "type": content_type, "source": source_url}] * len(chunks)
    add_to_chromadb(chunk_ids, chunks, meta)

    sb.table("content_cache").insert({
        "content_type": content_type, "exam": exam,
        "title": title, "source_url": source_url,
        "year": year, "subject": subject, "chroma_ids": chunk_ids,
    }).execute()

    return f"fetched:{title}"

def _fetch_pdf(url: str) -> list:
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        doc = fitz.open(stream=r.content, filetype="pdf")
        text = "\n".join(p.get_text() for p in doc)
        return splitter.split_text(text)
    except Exception:
        return []

def _fetch_webpage(url: str) -> list:
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return splitter.split_text(text)
    except Exception:
        return []
