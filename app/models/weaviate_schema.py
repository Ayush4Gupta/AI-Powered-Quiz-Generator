# weaviate_schema.py
import weaviate
from weaviate.util import generate_uuid5

DOC_CLASS = {
    "class": "DocumentChunk",
    "properties": [
        {"name": "text", "dataType": ["text"]},
        {"name": "topic", "dataType": ["text"]},
        {"name": "chapter", "dataType": ["number"]},
        {"name": "session_id", "dataType": ["text"]},
        {"name": "filename", "dataType": ["text"]},
        {"name": "upload_timestamp", "dataType": ["number"]},
    ],
    "vectorIndexType": "hnsw",
    "description": "Chunks of uploaded PDFs with session isolation."
}

def bootstrap_schema(client: weaviate.Client) -> None:
    """Initialize Weaviate schema if it doesn't exist"""
    try:
        if not client.schema.contains(DOC_CLASS):
            client.schema.create_class(DOC_CLASS)
            print(f"✅ Created Weaviate schema: {DOC_CLASS['class']}")
        else:
            print(f"✅ Weaviate schema already exists: {DOC_CLASS['class']}")
    except Exception as e:
        print(f"❌ Error creating Weaviate schema: {e}")
        raise

def ensure_schema_exists():
    """Ensure Weaviate schema is initialized on startup"""
    from app.core.settings import get_settings
    settings = get_settings()
    
    try:
        client = weaviate.Client(settings.weaviate_url)
        bootstrap_schema(client)
        return True
    except Exception as e:
        print(f"❌ Failed to initialize Weaviate schema: {e}")
        return False


# New function for per-chunk topic upsert
def batch_upsert_per_chunk(client, texts, topics, chapter, vectors, session_id=None, filename=None, upload_timestamp=None):
    """
    Upsert chunks with optional topic assignment and session metadata.
    Args:
        client: weaviate.Client
        texts: list of chunk strings
        topics: list of topic strings or None (if None, topics will not be stored)
        chapter: chapter number or None
        vectors: list of embedding vectors
        session_id: session identifier for content isolation
        filename: original filename
        upload_timestamp: timestamp of upload
    """
    with client.batch as batch:
        batch.batch_size = 64
        for i, (t, v) in enumerate(zip(texts, vectors)):
            data_object = {"text": t, "chapter": chapter}
            
            # Add session metadata if provided
            if session_id:
                data_object["session_id"] = session_id
            if filename:
                data_object["filename"] = filename
            if upload_timestamp:
                data_object["upload_timestamp"] = upload_timestamp
                
            # Only add topic if it's provided
            if topics:
                data_object["topic"] = topics[i]
                
            batch.add_data_object(
                data_object=data_object,
                class_name="DocumentChunk",
                uuid=generate_uuid5(t),
                vector=v,
            )
