# tasks.py
from pathlib import Path
from celery import Celery
from app.core.settings import get_settings
from app.utils.pdf import extract_text
from app.utils.splitters import split_text
from app.utils.embeddings import embedding_function
from app.models.weaviate_schema import bootstrap_schema, batch_upsert_per_chunk
import weaviate, structlog, time
import os

_settings = get_settings()

# Ensure broker URL is set
broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')

celery_app = Celery(
    "tasks",
    broker=broker_url,
    backend=broker_url,  # Use same URL for backend
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True
)

# Configure Celery to track task states properly
celery_app.conf.update(
    task_track_started=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    result_expires=3600,  # Results expire after 1 hour
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_prefetch_multiplier=1,  # Don't prefetch tasks
    worker_send_task_events=True,  # Enable task events
    task_send_sent_event=True  # Enable task sent events
)

log = structlog.get_logger()

@celery_app.task(
    name="ingest_pdf",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3
)
def ingest_pdf(self, pdf_path: str, session_id: str, filename: str, upload_timestamp: int, clear_previous: bool = True) -> None:
    try:
        log.info("ingest.started", pdf=pdf_path, session_id=session_id, filename=filename, clear_previous=clear_previous)

        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"PDF file not found at {pdf_path}")

        text = extract_text(Path(pdf_path))
        if not text or not text.strip():
            raise ValueError("No text content extracted from PDF")


        chunks = split_text(text)
        if not chunks:
            raise ValueError("No text chunks generated from PDF content")

        # Create embeddings for each chunk individually
        vectors = [embedding_function(text=chunk) for chunk in chunks]

        # Sanitize Weaviate URL to remove spaces
        weaviate_url = getattr(_settings, 'weaviate_url', None)
        if weaviate_url:
            weaviate_url = str(weaviate_url).strip().replace(' ', '')
        client = weaviate.Client(weaviate_url)
        bootstrap_schema(client)
        from app.models.weaviate_schema import batch_upsert_per_chunk
        
        # Store chunks with session metadata, no chapter filtering during ingestion
        batch_upsert_per_chunk(
            client, 
            chunks, 
            None,  # No topics during ingestion
            None,  # No chapter filtering during ingestion - chapters determined at quiz generation
            vectors,
            session_id=session_id,
            filename=filename,
            upload_timestamp=upload_timestamp
        )

        log.info("ingest.completed", chunks=len(chunks))

        # Clean up file after successful processing
        try:
            if Path(pdf_path).exists():
                Path(pdf_path).unlink()
                log.info("ingest.cleanup.success", pdf=pdf_path)
        except Exception as e:
            log.error("ingest.cleanup.failed", error=str(e), pdf=pdf_path)

        return f"Successfully processed PDF: {len(chunks)} chunks indexed"

    except Exception as e:
        log.error("ingest.failed", error=str(e), pdf=pdf_path)
        # Only clean up file if this is the last retry
        if self.request.retries >= self.max_retries:
            try:
                if Path(pdf_path).exists():
                    Path(pdf_path).unlink()
                    log.info("ingest.cleanup.final_failure", pdf=pdf_path)
            except Exception as cleanup_err:
                log.error("ingest.cleanup.failed", error=str(cleanup_err), pdf=pdf_path)
        # Retry with exponential backoff
        retry_in = 5 * (2 ** self.request.retries)  # 5s, 10s, 20s
        raise self.retry(exc=e, countdown=retry_in)

@celery_app.task(
    name="generate_quiz",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3
)
def generate_quiz_task(self, topic: str, n: int, difficulty: str, level: str, num_variants: int = 1):
    try:
        # Check network connectivity before attempting quiz generation
        import socket
        try:
            socket.gethostbyname('api.groq.com')
        except (socket.gaierror, socket.error):
            raise Exception("Network connectivity issue: Cannot resolve external API hostnames. Please check your internet connection and try again.")
        
        from app.services.quiz_generation import generate_quiz_with_variants
        return generate_quiz_with_variants(topic, n, difficulty, level, num_variants)
    except Exception as e:
        log.error("quiz.generation.failed", error=str(e))
        # Retry with exponential backoff
        retry_in = 5 * (2 ** self.request.retries)  # 5s, 10s, 20s
        raise self.retry(exc=e, countdown=retry_in)

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 10})
def process_folder_task(self, folder_path: str, session_id: str, clear_previous: bool = True, recursive: bool = True):
    """
    Background task to process a folder of documents
    
    Args:
        folder_path: Path to folder containing documents
        session_id: Session ID for content isolation
        clear_previous: Whether to clear previous content in session
        recursive: Whether to scan subfolders
    """
    try:
        log.info("folder.processing.started", 
                folder_path=folder_path, 
                session_id=session_id,
                recursive=recursive)
        
        # Import here to avoid circular imports
        from app.services.document_loader import document_loader
        
        # Load documents from folder
        documents = document_loader.load_documents_from_folder(folder_path, recursive)
        
        if not documents:
            return f"No supported documents found in {folder_path}"
        
        # Process each document similar to PDF processing
        # Sanitize Weaviate URL to remove spaces
        weaviate_url = getattr(_settings, 'weaviate_url', None)
        if weaviate_url:
            weaviate_url = str(weaviate_url).strip().replace(' ', '')
        weaviate_client = weaviate.Client(weaviate_url)
        bootstrap_schema(weaviate_client)
        
        # Clear previous content if requested
        if clear_previous:
            log.info("folder.processing.clearing_previous", session_id=session_id)
            try:
                weaviate_client.batch.delete_objects(
                    class_name="DocumentChunk",
                    where={"path": ["session_id"], "operator": "Equal", "valueText": session_id}
                )
            except Exception as e:
                log.warning("folder.processing.clear_failed", session_id=session_id, error=str(e))
        
        total_chunks = 0
        processed_files = 0
        
        for doc in documents:
            try:
                # Split document into chunks
                chunks = split_text(doc.content)
                
                if not chunks:
                    log.warning("folder.processing.no_chunks", source=doc.metadata.source)
                    continue
                
                # Generate embeddings for each chunk individually (same as PDF processing)
                vectors = [embedding_function(text=chunk) for chunk in chunks]
                
                # Store chunks with session metadata (same pattern as PDF processing)
                batch_upsert_per_chunk(
                    weaviate_client, 
                    chunks, 
                    None,  # No topics during ingestion
                    None,  # No chapter filtering during ingestion
                    vectors,
                    session_id=session_id,
                    filename=doc.metadata.source,
                    upload_timestamp=None  # Could add timestamp if needed
                )
                
                total_chunks += len(chunks)
                processed_files += 1
                
                log.info("folder.processing.file_completed",
                        source=doc.metadata.source,
                        chunks_created=len(chunks),
                        file_size=doc.metadata.file_size)
                
            except Exception as e:
                log.error("folder.processing.file_failed", 
                         source=doc.metadata.source, 
                         error=str(e))
                continue
        
        result_message = f"Successfully processed {processed_files} files from folder: {total_chunks} chunks indexed"
        
        log.info("folder.processing.completed",
                folder_path=folder_path,
                session_id=session_id,
                files_processed=processed_files,
                total_files=len(documents),
                total_chunks=total_chunks)
        
        return result_message
        
    except Exception as e:
        log.error("folder.processing.failed", 
                 folder_path=folder_path, 
                 session_id=session_id, 
                 error=str(e))
        # Retry with exponential backoff
        retry_in = 10 * (2 ** self.request.retries)  # 10s, 20s, 40s
        raise self.retry(exc=e, countdown=retry_in)

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 20})
def process_articles_task(self, article_urls: list, quiz_config: dict, session_id: str, processing_options: dict):
    """
    Background task to process articles and generate quiz
    
    Args:
        article_urls: List of article URLs to process
        quiz_config: Quiz generation configuration
        session_id: Session ID for content isolation
        processing_options: Article processing options
    """
    try:
        log.info("articles.processing.started", 
                urls=article_urls, 
                session_id=session_id,
                quiz_config=quiz_config)
        
        # Import here to avoid circular imports
        from app.services.article_fetcher import article_fetcher
        
        # Fetch articles with processing options
        max_articles = processing_options.get('max_articles', 10)
        articles = article_fetcher.fetch_multiple_articles(article_urls, max_articles)
        
        if not articles:
            return f"No articles could be fetched from the provided URLs"
        
        # Sanitize Weaviate URL to remove spaces
        weaviate_url = getattr(_settings, 'weaviate_url', None)
        if weaviate_url:
            weaviate_url = str(weaviate_url).strip().replace(' ', '')
        weaviate_client = weaviate.Client(weaviate_url)
        bootstrap_schema(weaviate_client)
        
        # Clear previous content if requested
        combine_articles = processing_options.get('combine_articles', True)
        if combine_articles:
            log.info("articles.processing.clearing_previous", session_id=session_id)
            try:
                weaviate_client.batch.delete_objects(
                    class_name="DocumentChunk",
                    where={"path": ["session_id"], "operator": "Equal", "valueText": session_id}
                )
            except Exception as e:
                log.warning("articles.processing.clear_failed", session_id=session_id, error=str(e))
        
        # Process each article
        total_chunks = 0
        processed_articles = 0
        
        for article in articles:
            try:
                # Split article content into chunks
                chunks = split_text(article.content)
                
                if not chunks:
                    log.warning("articles.processing.no_chunks", url=article.url)
                    continue
                
                # Generate embeddings for each chunk individually
                vectors = [embedding_function(text=chunk) for chunk in chunks]
                
                # Store chunks with session metadata and article URL as filename
                batch_upsert_per_chunk(
                    weaviate_client, 
                    chunks, 
                    None,  # No topics during ingestion
                    None,  # No chapter filtering during ingestion
                    vectors,
                    session_id=session_id,
                    filename=article.url,  # Use URL as filename for identification
                    upload_timestamp=int(time.time())
                )
                
                total_chunks += len(chunks)
                processed_articles += 1
                
                log.info("articles.processing.article_completed",
                        url=article.url,
                        title=article.title,
                        chunks_created=len(chunks),
                        word_count=article.word_count)
                
            except Exception as e:
                log.error("articles.processing.article_failed", 
                         url=article.url, 
                         error=str(e))
                continue
        
        # Generate quiz using processed articles
        if total_chunks > 0:
            try:
                log.info("articles.quiz_generation.starting", 
                        session_id=session_id,
                        total_chunks=total_chunks,
                        quiz_config=quiz_config)
                
                from app.services.quiz_generation import generate_quiz_with_variants
                
                quiz_result = generate_quiz_with_variants(
                    topic=quiz_config['topic'],
                    n=quiz_config['num_questions'],
                    diff=quiz_config['difficulty'],
                    level=quiz_config['employee_level'],
                    num_variants=quiz_config['num_variants'],
                    session_id=session_id
                )
                
                result_message = {
                    "status": "completed",
                    "message": f"Successfully processed {processed_articles} articles and generated quiz: {total_chunks} chunks indexed",
                    "articles_processed": processed_articles,
                    "total_articles": len(article_urls),
                    "total_chunks": total_chunks,
                    "quiz": quiz_result
                }
                
                log.info("articles.processing.completed",
                        session_id=session_id,
                        articles_processed=processed_articles,
                        total_articles=len(article_urls),
                        total_chunks=total_chunks,
                        quiz_generated=True)
                
                return result_message
                
            except Exception as e:
                log.error("articles.quiz_generation.failed", 
                         session_id=session_id, 
                         error=str(e))
                # Return partial success - articles processed but quiz failed
                return {
                    "status": "partial_success",
                    "message": f"Articles processed successfully but quiz generation failed: {str(e)}",
                    "articles_processed": processed_articles,
                    "total_articles": len(article_urls),
                    "total_chunks": total_chunks,
                    "quiz_error": str(e)
                }
        else:
            return {
                "status": "failed",
                "message": "No content could be extracted from any of the provided articles",
                "articles_processed": 0,
                "total_articles": len(article_urls),
                "total_chunks": 0
            }
        
    except Exception as e:
        log.error("articles.processing.failed", 
                 article_urls=article_urls, 
                 session_id=session_id, 
                 error=str(e))
        # Retry with exponential backoff
        retry_in = 20 * (2 ** self.request.retries)  # 20s, 40s, 80s
        raise self.retry(exc=e, countdown=retry_in)


@celery_app.task(
    name="ingest_articles_task",
    bind=True, 
    autoretry_for=(Exception,), 
    retry_kwargs={'max_retries': 3, 'countdown': 20}
)
def ingest_articles_task(self, article_urls: list, session_id: str, clear_previous: bool = True, processing_options: dict = None):
    """
    Background task to ingest articles (content extraction and storage only, no quiz generation)
    
    Args:
        article_urls: List of article URLs to process
        session_id: Session ID for content isolation
        clear_previous: Whether to clear previous content before ingesting
        processing_options: Article processing options
    """
    try:
        log.info("articles.ingestion.started", 
                urls=article_urls, 
                session_id=session_id,
                clear_previous=clear_previous,
                processing_options=processing_options)
        
        # Import here to avoid circular imports
        from app.services.article_fetcher import article_fetcher
        
        # Fetch articles with processing options
        max_articles = processing_options.get('max_articles', 10) if processing_options else 10
        articles = article_fetcher.fetch_multiple_articles(article_urls, max_articles)
        
        if not articles:
            return {
                "status": "failed",
                "message": "No articles could be fetched from the provided URLs",
                "articles_processed": 0,
                "total_articles": len(article_urls),
                "total_chunks": 0
            }
        
        # Sanitize Weaviate URL to remove spaces
        weaviate_url = getattr(_settings, 'weaviate_url', None)
        if weaviate_url:
            weaviate_url = str(weaviate_url).strip().replace(' ', '')
        weaviate_client = weaviate.Client(weaviate_url)
        bootstrap_schema(weaviate_client)
        
        # Clear previous content if requested
        if clear_previous:
            log.info("articles.ingestion.clearing_previous", session_id=session_id)
            try:
                weaviate_client.batch.delete_objects(
                    class_name="DocumentChunk",
                    where={"path": ["session_id"], "operator": "Equal", "valueText": session_id}
                )
            except Exception as e:
                log.warning("articles.ingestion.clear_failed", session_id=session_id, error=str(e))
        
        # Process each article
        total_chunks = 0
        processed_articles = 0
        
        for article in articles:
            try:
                # Split article content into chunks
                chunks = split_text(article.content)
                
                if not chunks:
                    log.warning("articles.ingestion.no_chunks", url=article.url)
                    continue
                
                # Generate embeddings for each chunk individually
                vectors = [embedding_function(text=chunk) for chunk in chunks]
                
                # Store chunks with session metadata and article URL as filename
                batch_upsert_per_chunk(
                    weaviate_client, 
                    chunks, 
                    None,  # No topics during ingestion
                    None,  # No chapter filtering during ingestion
                    vectors,
                    session_id=session_id,
                    filename=article.url,  # Use URL as filename for identification
                    upload_timestamp=int(time.time())
                )
                
                total_chunks += len(chunks)
                processed_articles += 1
                
                log.info("articles.ingestion.article_completed",
                        url=article.url,
                        title=article.title,
                        chunks_created=len(chunks),
                        word_count=article.word_count)
                
            except Exception as e:
                log.error("articles.ingestion.article_failed", 
                         url=article.url, 
                         error=str(e))
                continue
        
        # Return ingestion results (no quiz generation)
        result_message = {
            "status": "completed",
            "message": f"Successfully ingested {processed_articles} articles: {total_chunks} chunks indexed",
            "articles_processed": processed_articles,
            "total_articles": len(article_urls),
            "total_chunks": total_chunks
        }
        
        log.info("articles.ingestion.completed",
                session_id=session_id,
                articles_processed=processed_articles,
                total_articles=len(article_urls),
                total_chunks=total_chunks)
        
        return result_message
        
    except Exception as e:
        log.error("articles.ingestion.failed", 
                 article_urls=article_urls, 
                 session_id=session_id, 
                 error=str(e))
        # Retry with exponential backoff
        retry_in = 20 * (2 ** self.request.retries)  # 20s, 40s, 80s
        raise self.retry(exc=e, countdown=retry_in)

