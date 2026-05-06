import chromadb
from chromadb.utils import embedding_functions
from core.constants import CHROMA_PATH, COLLECTION_NAME, OPENAI_API_KEY, EMBED_MODEL

def get_collection():
    """
    Connects to the existing ChromaDB collection on disk.
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found. Check your .env file.")
    
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name=EMBED_MODEL,
    )
    return client.get_collection(name=COLLECTION_NAME, embedding_function=embed_fn)

def get_or_create_collection():
    """
    Connects to or creates the ChromaDB collection on disk.
    Used by ingestion.
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found. Check your .env file.")
        
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name=EMBED_MODEL,
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
