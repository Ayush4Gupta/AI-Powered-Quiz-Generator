# embeddings.py
from langchain_community.embeddings import HuggingFaceEmbeddings
from app.core.settings import get_settings

_settings = get_settings()

# Create a global instance to avoid reloading the model every time
_embedder = None

def get_embedder():
    """Get singleton embedder instance"""
    global _embedder
    if _embedder is None:
        _embedder = HuggingFaceEmbeddings(model_name=_settings.embedding_model_name)
    return _embedder

def embedding_function(text):
    embedder = get_embedder()
    # Accept both str and list[str]
    if isinstance(text, str):
        return embedder.embed_documents([text])[0]
    elif isinstance(text, list):
        return embedder.embed_documents(text)
    else:
        raise ValueError("embedding_function expects a str or list of str")
