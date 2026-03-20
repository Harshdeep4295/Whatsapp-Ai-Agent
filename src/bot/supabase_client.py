from supabase import create_client
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_sb = None


def get_sb():
    global _sb
    if _sb is None:
        _sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _sb
