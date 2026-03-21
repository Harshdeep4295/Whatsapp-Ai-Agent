import os
from dotenv import load_dotenv
load_dotenv()

WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_ACCESS_TOKEN    = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_VERIFY_TOKEN    = os.getenv("WHATSAPP_VERIFY_TOKEN")
GROQ_API_KEY             = os.getenv("GROQ_API_KEY")
CEREBRAS_API_KEY         = os.getenv("CEREBRAS_API_KEY", "")
TOGETHER_API_KEY         = os.getenv("TOGETHER_API_KEY", "")
SUPABASE_URL             = os.getenv("SUPABASE_URL")
SUPABASE_KEY             = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY     = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
CHROMA_PATH              = os.getenv("CHROMA_PATH", "./data/chroma_db")
PDFS_PATH                = os.getenv("PDFS_PATH", "./data/pdfs")
ADMIN_CHAT_ID            = os.getenv("ADMIN_CHAT_ID", "")
TAVILY_API_KEY           = os.getenv("TAVILY_API_KEY", "")
