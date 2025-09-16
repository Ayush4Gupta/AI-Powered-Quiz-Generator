import weaviate, structlog, cohere
from app.core.settings import get_settings
from app.utils.embeddings import embedding_function
import socket

settings = get_settings()
log = structlog.get_logger()
client = weaviate.Client(settings.weaviate_url)

def check_network_connectivity() -> bool:
    """Check if we can reach external APIs"""
    try:
        # Try to resolve DNS first
        socket.gethostbyname('api.cohere.ai')
        return True
    except (socket.gaierror, socket.error):
        return False

def get_cohere_client():
    """Get Cohere client with network check"""
    if not check_network_connectivity():
        log.warning("search.cohere_connectivity_failed", message="Cannot resolve Cohere API hostname")
        return None
    try:
        return cohere.Client(settings.cohere_api_key)
    except Exception as e:
        log.error("search.cohere_init_failed", error=str(e))
        return None

co = get_cohere_client()

def relevant_passages(topic: str, session_id: str = None, k: int = 20) -> list[str]:
    """
    Runs:
    1. Hybrid search using user topic (searching in TEXT content, not topic field)
    2. Vector search using HyDE synthetic doc
    3. Merges results, deduplicates, reranks
    
    Args:
        topic: Search topic
        session_id: Optional session filter to search only specific upload session
        k: Number of results to return
    
    Returns:
        List of relevant text passages (empty if no session_id provided)
    """
    try:
        # If no session_id provided, return empty to force general knowledge
        if not session_id:
            log.info("search.no_session", topic=topic, reason="No session_id provided - using general knowledge")
            return []
        
        cleaned_topic = topic.lower().strip().replace("what is ", "").replace("what are ", "").replace("?", "")
        log.info("search.start", original_topic=topic, cleaned_topic=cleaned_topic, session_id=session_id)

        # Generate synthetic document for HyDE
        synthetic_doc = cleaned_topic
        try:
            if co is None:
                log.warning("search.hyde_skipped", reason="Cohere client not available")
                synthetic_doc = cleaned_topic
            else:
                prompt = f"Write a detailed paragraph explaining the topic: {cleaned_topic}"
                synthetic_response = co.generate(prompt=prompt, max_tokens=300, temperature=0.5)
                synthetic_doc = synthetic_response.generations[0].text.strip()
                log.info("search.hyde_generated", synthetic_doc=synthetic_doc[:150])
        except Exception as e:
            log.warning("search.hyde_failed", error=str(e))
            synthetic_doc = cleaned_topic

        # Embed synthetic doc
        hyde_vector = None
        try:
            hyde_vector = embedding_function(synthetic_doc)
        except Exception as e:
            log.warning("search.embedding_failed", error=str(e))

        # Where clause for filtering by session
        where_filter = None
        filters = []
        
        # ALWAYS add session filter - this is mandatory for content isolation
        filters.append({"path": ["session_id"], "operator": "Equal", "valueText": session_id})
        
        # Single filter for session only
        if len(filters) == 1:
            where_filter = filters[0]
        elif len(filters) > 1:
            where_filter = {"operator": "And", "operands": filters}

        # Strategy 1: Hybrid search using topic as query (searches in TEXT content)
        hybrid_chunks = []
        try:
            hybrid_query = (
                client.query
                .get("DocumentChunk", ["text", "topic"])
                .with_limit(k * 2)
                .with_hybrid(query=cleaned_topic, alpha=0.5)  # This searches in TEXT content
            )
            if where_filter:
                hybrid_query = hybrid_query.with_where(where_filter)
            hybrid_result = hybrid_query.do()
            
            # Safe extraction with None checks
            if hybrid_result and "data" in hybrid_result:
                data = hybrid_result["data"]
                if data and "Get" in data:
                    get_data = data["Get"]
                    if get_data and "DocumentChunk" in get_data:
                        hybrid_chunks = get_data["DocumentChunk"] or []
            
            log.info("search.hybrid_complete", chunks_found=len(hybrid_chunks) if hybrid_chunks else 0)
        except Exception as e:
            log.error("search.hybrid_error", error=str(e))
            hybrid_chunks = []

        # Strategy 2: Vector search using HyDE synthetic document
        vector_chunks = []
        try:
            if hyde_vector:
                vector_query = (
                    client.query
                    .get("DocumentChunk", ["text", "topic"])
                    .with_limit(k * 2)
                    .with_near_vector({"vector": hyde_vector, "certainty": 0.6})
                )
                if where_filter:
                    vector_query = vector_query.with_where(where_filter)
                vector_result = vector_query.do()
                
                # Safe extraction with None checks
                if vector_result and "data" in vector_result:
                    data = vector_result["data"]
                    if data and "Get" in data:
                        get_data = data["Get"]
                        if get_data and "DocumentChunk" in get_data:
                            vector_chunks = get_data["DocumentChunk"] or []
                
                log.info("search.vector_complete", chunks_found=len(vector_chunks) if vector_chunks else 0)
            else:
                log.warning("search.vector_skipped", reason="No HyDE vector available")
        except Exception as e:
            log.error("search.vector_error", error=str(e))
            vector_chunks = []

        # Strategy 3: Fallback BM25 search if both above fail
        if len(hybrid_chunks) == 0 and len(vector_chunks) == 0:
            try:
                log.info("search.fallback_bm25", reason="No results from hybrid/vector search")
                fallback_query = (
                    client.query
                    .get("DocumentChunk", ["text", "topic"])
                    .with_limit(k)
                    .with_bm25(query=cleaned_topic)
                )
                if where_filter:
                    fallback_query = fallback_query.with_where(where_filter)
                fallback_result = fallback_query.do()
                
                # Safe extraction with None checks
                fallback_chunks = []
                if fallback_result and "data" in fallback_result:
                    data = fallback_result["data"]
                    if data and "Get" in data:
                        get_data = data["Get"]
                        if get_data and "DocumentChunk" in get_data:
                            fallback_chunks = get_data["DocumentChunk"] or []
                
                log.info("search.fallback_complete", chunks_found=len(fallback_chunks) if fallback_chunks else 0)
                # Use fallback as our primary results
                hybrid_chunks = fallback_chunks
            except Exception as e:
                log.error("search.fallback_error", error=str(e))

        # Ensure both are lists, never None
        if hybrid_chunks is None:
            hybrid_chunks = []
        if vector_chunks is None:
            vector_chunks = []

        # Combine and deduplicate
        all_chunks = hybrid_chunks + vector_chunks
        seen = set()
        deduped = []
        for chunk in all_chunks:
            text = chunk.get("text", "")
            if text and text not in seen:
                seen.add(text)
                deduped.append(text)

        log.info("search.combined_results", hybrid_count=len(hybrid_chunks), vector_count=len(vector_chunks), deduped_count=len(deduped))

        # If no results, return empty list
        if not deduped:
            log.warning("search.no_results", topic=topic)
            return []

        # Rerank all results using Cohere
        try:
            if co is None:
                log.warning("search.rerank_skipped", reason="Cohere client not available")
                return deduped[:k]
            else:
                reranked = co.rerank(query=cleaned_topic, documents=deduped, top_n=min(k, len(deduped)))
                sorted_chunks = [deduped[result.index] for result in reranked.results]
                log.info("search.rerank_success", final_count=len(sorted_chunks))
                return sorted_chunks
        except Exception as e:
            log.warning("search.rerank_failed", error=str(e))
            return deduped[:k]

    except Exception as e:
        log.error("search.pipeline_failure", topic=topic, error=str(e))
        return []

def debug_indexed_topics(limit: int = 20) -> dict:
    """Debug function to see what chunks are actually indexed in Weaviate"""
    try:
        log.info("debug.checking_indexed_content")
        # Get all chunks without any filters
        raw = (
            client.query
            .get("DocumentChunk", ["text"])
            .with_limit(limit)
            .do()
        )
        if not raw.get("data", {}).get("Get", {}).get("DocumentChunk"):
            log.warning("debug.no_indexed_content")
            return {"chunks": [], "total_chunks": 0}
        chunks = raw["data"]["Get"]["DocumentChunk"]
        # Prepare a summary of chunks and text preview
        chunk_summaries = []
        for chunk in chunks:
            text_preview = chunk.get("text", "")[:120] + ("..." if len(chunk.get("text", "")) > 120 else "")
            chunk_summaries.append({"text_preview": text_preview})
        log.info("debug.indexed_content", total_chunks=len(chunks))
        return {
            "chunks": chunk_summaries,
            "total_chunks": len(chunks)
        }
    except Exception as e:
        log.error("debug.error", error=str(e))
        return {"error": str(e), "chunks": [], "total_chunks": 0}

def debug_search_detailed(topic: str) -> dict:
    """Detailed debug function to diagnose search issues"""
    debug_info = {
        "original_topic": topic,
        "cleaned_topic": None,
        "normalized_query": None,
        "total_documents": 0,
        "exact_matches": 0,
        "fuzzy_matches": 0,
        "semantic_matches": 0,
        "all_topics_sample": [],
        "search_strategies": {},
        "errors": []
    }
    
    try:
        # Clean and normalize the topic
        cleaned_topic = topic.lower().strip()
        cleaned_topic = cleaned_topic.replace("what is ", "").replace("what are ", "").replace("?", "").strip()
        debug_info["cleaned_topic"] = cleaned_topic
        debug_info["normalized_query"] = cleaned_topic
        
        # Get total document count
        try:
            total_result = client.query.aggregate("DocumentChunk").with_meta_count().do()
            debug_info["total_documents"] = total_result.get('data', {}).get('Aggregate', {}).get('DocumentChunk', [{}])[0].get('meta', {}).get('count', 0)
        except Exception as e:
            debug_info["errors"].append(f"Count error: {str(e)}")
        
        # Get sample of all topics
        try:
            sample_result = client.query.get("DocumentChunk", ["topic"]).with_limit(20).do()
            if sample_result.get("data", {}).get("Get", {}).get("DocumentChunk"):
                topics = [d.get("topic", "N/A") for d in sample_result["data"]["Get"]["DocumentChunk"]]
                debug_info["all_topics_sample"] = list(set(topics))  # Unique topics
        except Exception as e:
            debug_info["errors"].append(f"Sample topics error: {str(e)}")
        
        # Test exact match strategy
        try:
            where_exact = {
                "path": ["topic"], "operator": "Equal", "valueString": topic
            }
            
            raw_exact = (
                client.query
                .get("DocumentChunk", ["text", "topic"])
                .with_hybrid(query=topic, alpha=0.5)
                .with_where(where_exact)
                .with_limit(10)
                .do()
            )
            
            if raw_exact.get("data", {}).get("Get", {}).get("DocumentChunk"):
                debug_info["exact_matches"] = len(raw_exact["data"]["Get"]["DocumentChunk"])
                debug_info["search_strategies"]["exact"] = "success"
            else:
                debug_info["search_strategies"]["exact"] = "no_results"
                
        except Exception as e:
            debug_info["errors"].append(f"Exact search error: {str(e)}")
            debug_info["search_strategies"]["exact"] = f"error: {str(e)}"
        
        # Test fuzzy match strategy
        try:
            where_fuzzy = {
                "path": ["topic"], "operator": "Like", "valueString": f"*{cleaned_topic}*"
            }
            
            raw_fuzzy = (
                client.query
                .get("DocumentChunk", ["text", "topic"])
                .with_hybrid(query=cleaned_topic, alpha=0.5)
                .with_where(where_fuzzy)
                .with_limit(10)
                .do()
            )
            
            if raw_fuzzy.get("data", {}).get("Get", {}).get("DocumentChunk"):
                debug_info["fuzzy_matches"] = len(raw_fuzzy["data"]["Get"]["DocumentChunk"])
                debug_info["search_strategies"]["fuzzy"] = "success"
            else:
                debug_info["search_strategies"]["fuzzy"] = "no_results"
                
        except Exception as e:
            debug_info["errors"].append(f"Fuzzy search error: {str(e)}")
            debug_info["search_strategies"]["fuzzy"] = f"error: {str(e)}"
        
        # Test semantic search (no topic filter)
        try:
            raw_semantic = (
                client.query
                .get("DocumentChunk", ["text", "topic"]) 
                .with_hybrid(query=cleaned_topic, alpha=0.3)
                .with_limit(10)
                .do()
            )
            
            if raw_semantic.get("data", {}).get("Get", {}).get("DocumentChunk"):
                debug_info["semantic_matches"] = len(raw_semantic["data"]["Get"]["DocumentChunk"])
                debug_info["search_strategies"]["semantic"] = "success"
            else:
                debug_info["search_strategies"]["semantic"] = "no_results"
                
        except Exception as e:
            debug_info["errors"].append(f"Semantic search error: {str(e)}")
            debug_info["search_strategies"]["semantic"] = f"error: {str(e)}"
        
        return debug_info
        
    except Exception as e:
        debug_info["errors"].append(f"General error: {str(e)}")
        return debug_info

def get_indexed_topics_and_content() -> dict:
    """Get all indexed chunks and sample content for debugging"""
    try:
        # Get all chunks
        result = client.query.get("DocumentChunk", ["text"]).with_limit(1000).do()
        if not result.get("data", {}).get("Get", {}).get("DocumentChunk"):
            return {"total_chunks": 0, "sample_content": []}
        chunks = result["data"]["Get"]["DocumentChunk"]
        # Sample content for first few chunks
        sample_content = []
        for chunk in chunks[:5]:
            sample_text = chunk.get("text", "")[:200] + ("..." if len(chunk.get("text", "")) > 200 else "")
            sample_content.append({
                "text_preview": sample_text
            })
        return {
            "total_chunks": len(chunks),
            "sample_content": sample_content
        }
    except Exception as e:
        log.error("debug.get_indexed_content.error", error=str(e))
        return {"error": str(e), "total_chunks": 0, "sample_content": []}

def get_session_content_types(session_id: str) -> list[str]:
    """
    Get the content types stored in a session by examining the filename extensions.
    Returns a list of content types like ['pdf', 'article', 'docx', etc.]
    """
    try:
        log.info("session.content_types.check", session_id=session_id)
        
        # Query for all chunks in the session with filename metadata
        result = client.query.get("DocumentChunk", ["filename"]).with_where({
            "path": ["session_id"], 
            "operator": "Equal", 
            "valueText": session_id
        }).with_limit(1000).do()
        
        if not result.get("data", {}).get("Get", {}).get("DocumentChunk"):
            log.warning("session.content_types.no_content", session_id=session_id)
            return []
        
        chunks = result["data"]["Get"]["DocumentChunk"]
        content_types = []
        
        for chunk in chunks:
            filename = chunk.get("filename", "")
            if filename:
                content_type = detect_content_type_from_filename(filename)
                if content_type:
                    content_types.append(content_type)
        
        # Remove duplicates while preserving order
        unique_types = list(dict.fromkeys(content_types))
        
        log.info("session.content_types.detected", 
                session_id=session_id, 
                content_types=unique_types,
                total_chunks=len(chunks))
        
        return unique_types
        
    except Exception as e:
        log.error("session.content_types.error", session_id=session_id, error=str(e))
        return []

def detect_content_type_from_filename(filename: str) -> str:
    """
    Detect content type from filename or URL.
    Returns: 'pdf', 'article', 'docx', 'pptx', 'txt', 'mixed', or 'unknown'
    """
    if not filename:
        return "unknown"
    
    filename_lower = filename.lower()
    
    # Check for URL patterns (articles)
    if filename_lower.startswith(('http://', 'https://')):
        return "article"
    
    # Check file extensions
    if filename_lower.endswith('.pdf'):
        return "pdf"
    elif filename_lower.endswith(('.doc', '.docx')):
        return "docx"
    elif filename_lower.endswith(('.ppt', '.pptx')):
        return "pptx"
    elif filename_lower.endswith('.txt'):
        return "txt"
    elif filename_lower.endswith(('.html', '.htm')):
        return "article"
    else:
        # Check for common article patterns in filename
        article_indicators = ['article', 'blog', 'news', 'post', 'medium.com', 'substack', 'wikipedia']
        for indicator in article_indicators:
            if indicator in filename_lower:
                return "article"
        
        return "unknown"


def get_all_session_content(session_id: str, k: int = 100) -> list[str]:
    """
    Get all indexed content from a session regardless of topic
    
    Args:
        session_id: Session ID to filter content
        k: Maximum number of passages to return
    
    Returns:
        List of text passages from all content in the session
    """
    try:
        log.info("search.all_session_content.start", session_id=session_id, max_results=k)
        
        # Query for all chunks in the session
        where_filter = {
            "path": ["session_id"],
            "operator": "Equal",
            "valueText": session_id
        }
        
        result = client.query.get("DocumentChunk", ["text", "filename"]) \
            .with_where(where_filter) \
            .with_limit(k) \
            .do()
        
        if not result.get("data", {}).get("Get", {}).get("DocumentChunk"):
            log.info("search.all_session_content.no_results", session_id=session_id)
            return []
        
        chunks = result["data"]["Get"]["DocumentChunk"]
        passages = [chunk["text"] for chunk in chunks if chunk.get("text")]
        
        log.info("search.all_session_content.complete", 
                session_id=session_id, 
                total_chunks=len(chunks),
                passages_returned=len(passages))
        
        return passages
        
    except Exception as e:
        log.error("search.all_session_content.error", session_id=session_id, error=str(e))
        return []
