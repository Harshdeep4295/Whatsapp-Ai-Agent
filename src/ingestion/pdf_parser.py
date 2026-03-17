import fitz  # PyMuPDF
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

def extract_text_from_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)

def chunk_text(text: str, source: str) -> list:
    chunks = splitter.split_text(text)
    return [{"text": c, "source": source} for c in chunks]

def process_pdf(pdf_path: str) -> list:
    fname = os.path.basename(pdf_path)
    text = extract_text_from_pdf(pdf_path)
    return chunk_text(text, source=fname)
