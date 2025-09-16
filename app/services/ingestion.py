from tempfile import NamedTemporaryFile
from fastapi import UploadFile, HTTPException
from app.background.tasks import ingest_pdf
import structlog
import os
import uuid
import time

log = structlog.get_logger()

def enqueue_ingestion(file: UploadFile, session_id: str = None, clear_previous: bool = True):
    """
    Enqueue PDF ingestion task with session management and vector cleanup.
    """
    try:
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        log.info("ingest.request.received",
                filename=getattr(file, 'filename', None),
                session_id=session_id,
                clear_previous=clear_previous)

        # Validate file type
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            log.warning("ingest.invalid_filetype", filename=getattr(file, 'filename', None))
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        # Validate file size (e.g., max 50MB)
        try:
            file.file.seek(0, 2)  # Seek to end
            file_size = file.file.tell()
            file.file.seek(0)  # Reset to beginning
        except Exception as e:
            log.error("ingest.file_size_check_failed", error=str(e))
            raise HTTPException(status_code=400, detail="Failed to validate file size")

        if file_size > 50 * 1024 * 1024:  # 50MB limit
            log.warning("ingest.file_too_large", size=file_size)
            raise HTTPException(status_code=400, detail="File size must be less than 50MB")

        if file_size == 0:
            log.warning("ingest.empty_file")
            raise HTTPException(status_code=400, detail="File is empty")

        # Use persistent uploads directory
        uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'uploads')
        uploads_dir = os.path.abspath(uploads_dir)
        try:
            os.makedirs(uploads_dir, exist_ok=True)
            log.info("ingest.uploads_dir", uploads_dir=uploads_dir)
        except Exception as e:
            log.error("ingest.uploads_dir_failed", error=str(e), uploads_dir=uploads_dir)
            raise HTTPException(status_code=500, detail=f"Failed to create uploads directory: {str(e)}")

        safe_filename = file.filename.replace(' ', '_')
        upload_path = os.path.join(uploads_dir, f"quiz_upload_{safe_filename}")
        log.info("ingest.upload_path", upload_path=upload_path)

        # Read file content in chunks to handle large files
        content = bytearray()
        try:
            while chunk := file.file.read(8192):
                content.extend(chunk)
        except Exception as e:
            log.error("ingest.read_failed", error=str(e), filename=file.filename)
            raise HTTPException(status_code=500, detail=f"Failed to read uploaded file: {str(e)}")

        if not content:
            log.warning("ingest.empty_content")
            raise HTTPException(status_code=400, detail="File content is empty")

        # Write to persistent upload file
        try:
            with open(upload_path, 'wb') as f:
                f.write(content)
            log.info("ingest.file_saved", upload_path=upload_path, size=len(content))
        except Exception as e:
            log.error("ingest.file_save_failed", error=str(e), upload_path=upload_path)
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

        # Enqueue the task with session management
        try:
            current_timestamp = int(time.time())
            task = ingest_pdf.delay(
                upload_path, 
                session_id, 
                file.filename, 
                current_timestamp, 
                clear_previous
            )
            if not task or not task.id:
                raise ValueError("No task ID received from Celery")

            log.info("ingest.enqueued",
                    task_id=task.id,
                    filename=file.filename,
                    file_size=file_size,
                    session_id=session_id,
                    clear_previous=clear_previous)
            return {"task_id": task.id, "session_id": session_id}
        except Exception as e:
            log.error("ingest.celery_enqueue_failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to enqueue ingestion task: {str(e)}")

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        log.error("ingest.unhandled_error", error=str(e), filename=getattr(file, 'filename', 'unknown'))
        raise HTTPException(status_code=500, detail=f"Failed to process PDF upload: {str(e)}")

def enqueue_folder_ingestion(folder_path: str, session_id: str = None, clear_previous: bool = True, recursive: bool = True):
    """
    Enqueue folder processing task with session management.
    
    Args:
        folder_path: Path to folder containing documents
        session_id: Session ID for content isolation
        clear_previous: Whether to clear previous content in session
        recursive: Whether to scan subfolders
        
    Returns:
        Dict with task_id and session_id
    """
    try:
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        log.info("folder_ingest.request.received",
                folder_path=folder_path,
                session_id=session_id,
                clear_previous=clear_previous,
                recursive=recursive)

        # Validate folder path
        if not os.path.exists(folder_path):
            log.warning("folder_ingest.invalid_path", folder_path=folder_path)
            raise HTTPException(status_code=400, detail=f"Folder does not exist: {folder_path}")
        
        if not os.path.isdir(folder_path):
            log.warning("folder_ingest.not_directory", folder_path=folder_path)
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {folder_path}")

        # Check if folder contains any supported files
        from app.services.document_loader import document_loader
        try:
            supported_files = document_loader.scan_folder(folder_path, recursive)
            if not supported_files:
                from app.utils.document_extractors import get_supported_extensions
                supported_exts = ', '.join(get_supported_extensions())
                raise HTTPException(
                    status_code=400, 
                    detail=f"No supported files found in folder. Supported types: {supported_exts}"
                )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        try:
            # Enqueue background task
            from app.background.tasks import process_folder_task
            task = process_folder_task.delay(
                folder_path=folder_path,
                session_id=session_id,
                clear_previous=clear_previous,
                recursive=recursive
            )
            
            log.info("folder_ingest.task.enqueued",
                    task_id=task.id,
                    folder_path=folder_path,
                    session_id=session_id,
                    files_found=len(supported_files))
            
            return {
                "task_id": task.id, 
                "session_id": session_id,
                "files_found": len(supported_files)
            }
            
        except Exception as e:
            log.error("folder_ingest.celery_enqueue_failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to enqueue folder processing task: {str(e)}")

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        log.error("folder_ingest.unhandled_error", error=str(e), folder_path=folder_path)
        raise HTTPException(status_code=500, detail=f"Failed to process folder: {str(e)}")

def enqueue_article_processing(article_urls: list, quiz_config: dict, session_id: str = None, processing_options: dict = None):
    """
    Enqueue article processing and quiz generation task.
    
    Args:
        article_urls: List of article URLs to process
        quiz_config: Quiz generation configuration dict
        session_id: Session ID for content isolation
        processing_options: Article processing options dict
        
    Returns:
        Dict with task_id and session_id
    """
    try:
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Set default processing options
        if not processing_options:
            processing_options = {
                'combine_articles': True,
                'max_articles': 10,
                'timeout_per_article': 30,
                'respect_delays': True
            }
        
        log.info("article_processing.request.received",
                article_count=len(article_urls),
                session_id=session_id,
                quiz_config=quiz_config,
                processing_options=processing_options)

        # Validate article URLs
        valid_urls = []
        for url in article_urls[:processing_options.get('max_articles', 10)]:
            if url and isinstance(url, str) and url.startswith(('http://', 'https://')):
                valid_urls.append(url)
            else:
                log.warning("article_processing.invalid_url", url=url)
        
        if not valid_urls:
            log.warning("article_processing.no_valid_urls")
            raise HTTPException(status_code=400, detail="No valid article URLs provided")

        # Enqueue the background task
        try:
            from app.background.tasks import process_articles_task
            
            task = process_articles_task.delay(
                article_urls=valid_urls,
                quiz_config=quiz_config,
                session_id=session_id,
                processing_options=processing_options
            )
            
            if not task or not task.id:
                raise ValueError("No task ID received from Celery")
            
            log.info("article_processing.task.enqueued",
                    task_id=task.id,
                    article_count=len(valid_urls),
                    session_id=session_id)
            
            return {
                "task_id": task.id, 
                "session_id": session_id,
                "articles_to_process": len(valid_urls)
            }
            
        except Exception as e:
            log.error("article_processing.celery_enqueue_failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to enqueue article processing task: {str(e)}")

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        log.error("article_processing.unhandled_error", error=str(e), article_count=len(article_urls) if article_urls else 0)
        raise HTTPException(status_code=500, detail=f"Failed to process article request: {str(e)}")


def enqueue_article_ingestion(article_urls: list, session_id: str = None, clear_previous: bool = True, processing_options: dict = None):
    """
    Enqueue article ingestion task (content extraction and storage only, no quiz generation).
    
    Args:
        article_urls: List of article URLs to ingest
        session_id: Session ID for content isolation
        clear_previous: Whether to clear previous content before ingesting
        processing_options: Article processing options dict
        
    Returns:
        Dict with task_id and session_id
    """
    try:
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Set default processing options
        if not processing_options:
            processing_options = {
                'max_articles': 10,
                'timeout_per_article': 30,
                'respect_delays': True
            }
        
        log.info("article_ingestion.request.received",
                article_count=len(article_urls),
                session_id=session_id,
                clear_previous=clear_previous,
                processing_options=processing_options)

        # Validate article URLs
        valid_urls = []
        for url in article_urls[:processing_options.get('max_articles', 10)]:
            if url and isinstance(url, str) and url.startswith(('http://', 'https://')):
                valid_urls.append(url)
            else:
                log.warning("article_ingestion.invalid_url", url=url)
        
        if not valid_urls:
            log.warning("article_ingestion.no_valid_urls")
            raise HTTPException(status_code=400, detail="No valid article URLs provided")

        # Enqueue the background task for ingestion only
        try:
            from app.background.tasks import ingest_articles_task
            
            task = ingest_articles_task.delay(
                article_urls=valid_urls,
                session_id=session_id,
                clear_previous=clear_previous,
                processing_options=processing_options
            )
            
            if not task or not task.id:
                raise ValueError("No task ID received from Celery")
            
            log.info("article_ingestion.task.enqueued",
                    task_id=task.id,
                    article_count=len(valid_urls),
                    session_id=session_id)
            
            return {
                "task_id": task.id, 
                "session_id": session_id,
                "articles_to_process": len(valid_urls)
            }
            
        except Exception as e:
            log.error("article_ingestion.celery_enqueue_failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to enqueue article ingestion task: {str(e)}")

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        log.error("article_ingestion.unhandled_error", error=str(e), article_count=len(article_urls) if article_urls else 0)
        raise HTTPException(status_code=500, detail=f"Failed to process article ingestion request: {str(e)}")
