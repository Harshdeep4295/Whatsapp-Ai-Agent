import chromadb
from chromadb.utils import embedding_functions
from config import CHROMA_PATH

_collection = None

def _get_col():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        _collection = client.get_or_create_collection(
            "exam_docs", embedding_function=ef
        )
    return _collection

def retrieve(query: str, n_results: int = 3) -> str:
    col = _get_col()
    if col.count() == 0:
        return ""
    results = col.query(query_texts=[query], n_results=n_results)
    docs = results["documents"][0]
    sources = [m.get("source", "") for m in results["metadatas"][0]]
    return "\n\n".join(f"[{src}]\n{doc}" for doc, src in zip(docs, sources))

def add_to_chromadb(ids: list, docs: list, metadatas: list):
    col = _get_col()
    col.add(ids=ids, documents=docs, metadatas=metadatas)
