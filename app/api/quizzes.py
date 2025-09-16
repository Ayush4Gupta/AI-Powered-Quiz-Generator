from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from celery.result import AsyncResult
from app.schemas.quizzes import *
from app.services.ingestion import enqueue_ingestion
from app.core.errors import QuizError
from app.core.settings import get_settings
import structlog

router = APIRouter(prefix="/quizzes")
log = structlog.get_logger()
settings = get_settings()

# Store the last generated quiz for easy export
_last_generated_quiz = None

# ---------- POST /quizzes/ingest ----------
@router.post("/ingest", response_model=IngestResponse, status_code=202, tags=["PDF Management"])
async def ingest_pdf(
    pdf: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    clear_previous: bool = Form(True)
):
    # Check Redis connectivity first
    try:
        from app.background.tasks import celery_app
        redis_conn = celery_app.backend.client
        if not redis_conn.ping():
            log.error("ingest_pdf.redis_connection_failed")
            raise QuizError.server_error("Redis connection failed - please check if Redis is running")
    except Exception as e:
        log.error("ingest_pdf.redis_check_failed", error=str(e))
        raise QuizError.server_error(f"Failed to verify Redis connection: {str(e)}")

    # Log incoming request details
    log.info("ingest_pdf.request_received", filename=pdf.filename, session_id=session_id, clear_previous=clear_previous)

    try:
        # Validate PDF file size before enqueuing
        pdf.file.seek(0, 2)  # Seek to end
        file_size = pdf.file.tell()
        pdf.file.seek(0)  # Reset to beginning
        
        if file_size > 50 * 1024 * 1024:  # 50MB limit
            log.error("ingest_pdf.file_too_large", size=file_size)
            raise QuizError.validation_error("PDF file size must be less than 50MB")

        result = enqueue_ingestion(pdf, session_id, clear_previous)
        job_id = result["task_id"]
        returned_session_id = result["session_id"]
        log.info("ingest_pdf.task_enqueued", job_id=job_id, session_id=returned_session_id)
        
        # Validate job_id before constructing response
        if not job_id or not isinstance(job_id, str):
            log.error("ingest_pdf.invalid_job_id", job_id=job_id)
            raise QuizError.server_error("Invalid job ID received from task queue")
            
        try:
            # Explicitly construct and validate response with session info
            response = IngestResponse(
                job_id=job_id,
                session_id=returned_session_id,
                message="PDF upload started. Use the poll endpoint to check status."
            )
            return response
        except Exception as e:
            log.error("ingest_pdf.response_construction_failed", job_id=job_id, error=str(e))
            raise QuizError.server_error(f"Failed to construct response: {str(e)}")
            
    except QuizError:
        raise
    except Exception as e:
        log.error("ingest_pdf.enqueue_failed", error=str(e))
        raise QuizError.server_error(f"Failed to enqueue ingestion: {str(e)}")

# ---------- POST /quizzes/ingest-folder ----------
@router.post("/ingest-folder", response_model=FolderExtractionResponse, status_code=202, tags=["PDF Management"])
async def ingest_folder(req: FolderExtractionRequest):
    """Process a folder containing multiple document types (PDF, DOCX, PPTX, TXT)"""
    try:
        from app.services.ingestion import enqueue_folder_ingestion
        from app.utils.document_extractors import get_supported_extensions
        
        log.info("ingest_folder.request_received", 
                folder_path=req.folder_path, 
                session_id=req.session_id,
                recursive=req.recursive)
        
        result = enqueue_folder_ingestion(
            folder_path=req.folder_path,
            session_id=req.session_id,
            clear_previous=req.clear_previous,
            recursive=req.recursive
        )
        
        job_id = result["task_id"]
        returned_session_id = result["session_id"]
        files_found = result["files_found"]
        
        log.info("ingest_folder.task_enqueued", 
                job_id=job_id, 
                session_id=returned_session_id,
                files_found=files_found)
        
        response = FolderExtractionResponse(
            job_id=job_id,
            session_id=returned_session_id,
            message=f"Folder processing started. Found {files_found} supported files. Use the poll endpoint to check status.",
            files_found=files_found,
            supported_types=get_supported_extensions()
        )
        return response
        
    except QuizError:
        raise
    except Exception as e:
        log.error("ingest_folder.failed", folder_path=req.folder_path, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process folder: {str(e)}")

# ---------- POST /quizzes/generate-from-articles ----------
@router.post("/ingest-articles", response_model=ArticleIngestionResponse, status_code=202, tags=["PDF Management"])
async def ingest_articles(req: ArticleIngestionRequest):
    """Ingest multiple article URLs into a session - returns task ID for polling"""
    try:
        # Check Redis connectivity first
        try:
            from app.background.tasks import celery_app
            redis_conn = celery_app.backend.client
            if not redis_conn.ping():
                log.error("ingest_articles.redis_connection_failed")
                raise QuizError.server_error("Redis connection failed - please check if Redis is running")
        except Exception as e:
            log.error("ingest_articles.redis_check_failed", error=str(e))
            raise QuizError.server_error(f"Failed to verify Redis connection: {str(e)}")

        log.info("ingest_articles.request_received", 
                article_count=len(req.articles),
                session_id=req.session_id)

        # Validate article URLs
        valid_articles = []
        for article in req.articles:
            if article.url and article.url.startswith(('http://', 'https://')):
                valid_articles.append(article.url)
            else:
                log.warning("ingest_articles.invalid_url", url=article.url)
        
        if not valid_articles:
            raise QuizError.validation_error("No valid article URLs provided. URLs must start with http:// or https://")
        
        if len(valid_articles) > req.processing_options.max_articles:
            log.warning("ingest_articles.too_many_urls", 
                       provided=len(valid_articles), 
                       max_allowed=req.processing_options.max_articles)
            valid_articles = valid_articles[:req.processing_options.max_articles]

        # Prepare processing options
        processing_options = {
            'max_articles': req.processing_options.max_articles,
            'timeout_per_article': req.processing_options.timeout_per_article,
            'respect_delays': req.processing_options.respect_delays
        }

        # Enqueue article ingestion only (no quiz generation)
        from app.services.ingestion import enqueue_article_ingestion
        
        result = enqueue_article_ingestion(
            article_urls=valid_articles,
            session_id=req.session_id,
            clear_previous=req.clear_previous,
            processing_options=processing_options
        )
        
        job_id = result["task_id"]
        returned_session_id = result["session_id"]
        articles_to_process = result["articles_to_process"]
        
        log.info("ingest_articles.task_enqueued", 
                job_id=job_id, 
                session_id=returned_session_id,
                articles_to_process=articles_to_process)
        
        response = ArticleIngestionResponse(
            job_id=job_id,
            session_id=returned_session_id,
            message=f"Article ingestion started. Processing {articles_to_process} articles. Use the poll endpoint to check status.",
            articles_to_process=articles_to_process
        )
        
        return response
        
    except QuizError:
        raise
    except Exception as e:
        log.error("ingest_articles.failed", error=str(e))
        raise QuizError.server_error(f"Failed to start article ingestion: {str(e)}")

# ---------- POST /quizzes/generate ----------

# ---------- POST /quizzes/generate ----------
@router.post("/generate", response_model=QuizResult, status_code=200, tags=["Quiz Generation"])
async def generate_quiz(req: GenerateRequest):
    """Generate quiz directly - returns quiz questions immediately (may take 10-30 seconds)"""
    global _last_generated_quiz
    
    if req.num_questions > settings.max_questions:
        raise QuizError.validation_error(f"num_questions must be ≤{settings.max_questions}")
    
    # Validate request parameters
    if req.use_all_content and req.topic:
        raise QuizError.validation_error("Cannot specify both topic and use_all_content=True. Use one or the other.")
    
    if not req.use_all_content and not req.topic:
        raise QuizError.validation_error("Must specify either a topic or set use_all_content=True")
    
    try:
        effective_topic = "All Indexed Content" if req.use_all_content else req.topic
        log.info("generate.started", 
                topic=effective_topic, 
                use_all_content=req.use_all_content,
                num_questions=req.num_questions, 
                num_variants=req.num_variants)
        
        # Track session usage if session_id is provided
        if hasattr(req, 'session_id') and req.session_id:
            try:
                from app.api.sessions import track_quiz_session_usage
                track_quiz_session_usage(req.session_id)
            except Exception as e:
                log.warning("generate.session_tracking_failed", session_id=req.session_id, error=str(e))
        
        # Import here to avoid circular imports
        from app.services.quiz_generation import generate_quiz_with_variants
        
        # Determine which session to use for content
        session_filter = req.session_id if hasattr(req, 'session_id') and req.session_id else None
        
        quiz_result = generate_quiz_with_variants(
            req.topic, req.num_questions, req.difficulty, req.employee_level, 
            req.num_variants, session_filter, req.use_all_content
        )
        
        if not quiz_result or not quiz_result.get("variants"):
            error_msg = "No questions could be generated from all indexed content" if req.use_all_content else f"No questions could be generated for topic: {req.topic}"
            raise QuizError.not_found(error_msg)
        
        # Store the last generated quiz for easy export
        _last_generated_quiz = {
            "topic": effective_topic,
            "use_all_content": req.use_all_content,
            "num_questions": req.num_questions,
            "difficulty": req.difficulty,
            "employee_level": req.employee_level,
            "num_variants": req.num_variants,
            "result": quiz_result
        }
            
        log.info("generate.completed", 
                topic=effective_topic, 
                use_all_content=req.use_all_content,
                num_variants=len(quiz_result["variants"]))
        return QuizResult(**quiz_result)
        
    except QuizError:
        raise
    except Exception as e:
        log.error("generate.failed", topic=req.topic, error=str(e))
        raise QuizError.server_error(f"Quiz generation failed: {str(e)}")

# ---------- GET /quizzes/pdf/{job_id} ----------
@router.get("/pdf/{job_id}", response_model=PollStatusResponse, tags=["PDF Management"])
async def poll_pdf_ingestion(job_id: str):
    """Poll PDF ingestion job status - only for PDF processing jobs"""
    try:
        res = AsyncResult(job_id)
        
        # Check if job exists in the result backend
        if res is None:
            return PollStatusResponse(job_id=job_id, status="not_found")
        
        # Handle different status states
        if res.status == 'PENDING':
            # Task is queued/pending - this is normal for new tasks
            return PollStatusResponse(job_id=job_id, status="pending")
        elif res.status == 'STARTED':
            # Task has started processing
            return PollStatusResponse(job_id=job_id, status="processing")
        elif res.status == 'SUCCESS':
            # Task completed successfully
            try:
                result = res.result
                if result is not None and str(result) != "None" and str(result).strip():
                    if isinstance(result, str):
                        return PollStatusResponse(job_id=job_id, status="completed", result=result)
                    elif isinstance(result, dict):
                        return PollStatusResponse(job_id=job_id, status="completed", result=result)
                    else:
                        return PollStatusResponse(job_id=job_id, status="completed", result=str(result))
                else:
                    return PollStatusResponse.model_construct(job_id=job_id, status="completed")
            except Exception as e:
                log.error("poll.pdf.result_error", job_id=job_id, error=str(e))
                return PollStatusResponse(job_id=job_id, status="failed", result=f"Error retrieving PDF processing result: {str(e)}")
        elif res.status == 'FAILURE':
            # Task failed
            try:
                error_info = str(res.result) if res.result else "Unknown error occurred"
                return PollStatusResponse(job_id=job_id, status="failed", result=error_info)
            except Exception:
                return PollStatusResponse(job_id=job_id, status="failed", result="PDF processing failed with unknown error")
        else:
            # Unknown status or other states (RETRY, REVOKED, etc.)
            return PollStatusResponse(job_id=job_id, status="processing")
    
    except AttributeError as e:
        if "DisabledBackend" in str(e):
            log.error("poll.pdf.backend_disabled", job_id=job_id, error=str(e))
            return PollStatusResponse(
                job_id=job_id, 
                status="failed", 
                result="Celery result backend is not configured. Please check Redis connection and restart the service."
            )
        else:
            log.error("poll.pdf.attribute_error", job_id=job_id, error=str(e))
            return PollStatusResponse(job_id=job_id, status="failed", result=f"Service configuration error: {str(e)}")
    
    except Exception as e:
        log.error("poll.pdf.unexpected_error", job_id=job_id, error=str(e))
        return PollStatusResponse(job_id=job_id, status="failed", result=f"Unexpected error: {str(e)}")

# ---------- GET /quizzes/poll/{job_id} ----------
@router.get("/poll/{job_id}", response_model=PollStatusResponse, tags=["Task Polling"])
async def poll_task_status(job_id: str):
    """Poll any task status - works for PDF, folder, and article processing jobs"""
    try:
        res = AsyncResult(job_id)
        
        # Check if job exists in the result backend
        if res is None:
            return PollStatusResponse(job_id=job_id, status="not_found")
        
        # Handle different status states
        if res.status == 'PENDING':
            # Task is queued/pending - this is normal for new tasks
            return PollStatusResponse(job_id=job_id, status="pending")
        elif res.status == 'STARTED':
            # Task has started processing
            return PollStatusResponse(job_id=job_id, status="processing")
        elif res.status == 'SUCCESS':
            # Task completed successfully
            try:
                result = res.result
                if result is not None and str(result) != "None" and str(result).strip():
                    if isinstance(result, str):
                        return PollStatusResponse(job_id=job_id, status="completed", result=result)
                    elif isinstance(result, dict):
                        # Check if this is a quiz generation result
                        if result.get("quiz"):
                            return PollStatusResponse(job_id=job_id, status="completed", result=result)
                        else:
                            return PollStatusResponse(job_id=job_id, status="completed", result=result)
                    else:
                        return PollStatusResponse(job_id=job_id, status="completed", result=str(result))
                else:
                    return PollStatusResponse.model_construct(job_id=job_id, status="completed")
            except Exception as e:
                log.error("poll.task.result_error", job_id=job_id, error=str(e))
                return PollStatusResponse(job_id=job_id, status="failed", result=f"Error retrieving task result: {str(e)}")
        elif res.status == 'FAILURE':
            # Task failed
            try:
                error_info = str(res.result) if res.result else "Unknown error occurred"
                return PollStatusResponse(job_id=job_id, status="failed", result=error_info)
            except Exception:
                return PollStatusResponse(job_id=job_id, status="failed", result="Task failed with unknown error")
        else:
            # Unknown status or other states (RETRY, REVOKED, etc.)
            return PollStatusResponse(job_id=job_id, status="processing")
    
    except AttributeError as e:
        if "DisabledBackend" in str(e):
            log.error("poll.task.backend_disabled", job_id=job_id, error=str(e))
            return PollStatusResponse(
                job_id=job_id, 
                status="failed", 
                result="Celery result backend is not configured. Please check Redis connection and restart the service."
            )
        else:
            log.error("poll.task.attribute_error", job_id=job_id, error=str(e))
            return PollStatusResponse(job_id=job_id, status="failed", result=f"Service configuration error: {str(e)}")
    
    except Exception as e:
        log.error("poll.task.unexpected_error", job_id=job_id, error=str(e))
        return PollStatusResponse(job_id=job_id, status="failed", result=f"Unexpected error: {str(e)}")

# ---------- GET /quizzes/debug/indexed-content ----------
@router.get("/debug/indexed-content", tags=["Debug & Diagnostics"])
async def debug_indexed_content():
    """Debug endpoint to see what content is indexed in Weaviate"""
    try:
        from app.services.search import debug_indexed_topics
        result = debug_indexed_topics(limit=50)
        if result is None:
            raise QuizError.server_error("Failed to retrieve indexed content")
        return result
    except QuizError:
        raise
    except Exception as e:
        log.error("debug.indexed_content.error", error=str(e))
        raise QuizError.server_error(f"Failed to retrieve indexed content: {str(e)}")

# ---------- GET /quizzes/debug/search/{topic} ----------
@router.get("/debug/search/{topic}", tags=["Debug & Diagnostics"])
async def debug_search_topic(topic: str, session_id: str):
    """Debug endpoint to test search functionality for a specific topic"""
    try:
        from app.services.search import relevant_passages
        passages = relevant_passages(topic, session_id, k=10)
        return {
            "topic": topic,
            "session_id": session_id, 
            "passages_found": len(passages),
            "passages": passages[:3] if passages else [],  # Show first 3 for brevity
            "has_content": len(passages) > 0
        }
    except Exception as e:
        log.error("debug.search_topic.error", topic=topic, error=str(e))
        raise QuizError.server_error(f"Failed to search topic: {str(e)}")

# ---------- GET /quizzes/debug/search-detailed/{topic} ----------
@router.get("/debug/search-detailed/{topic}", tags=["Debug & Diagnostics"])
async def debug_search_detailed_endpoint(topic: str):
    """Detailed debug endpoint to diagnose search issues"""
    try:
        from app.services.search import debug_search_detailed
        debug_info = debug_search_detailed(topic)
        if debug_info is None:
            raise QuizError.server_error("Failed to retrieve search details")
        return debug_info
    except QuizError:
        raise
    except Exception as e:
        log.error("debug.search_detailed.error", topic=topic, error=str(e))
        raise QuizError.server_error(f"Failed to retrieve search details: {str(e)}")

# ---------- GET /quizzes/debug/indexed-content-detailed ----------
@router.get("/debug/indexed-content-detailed", tags=["Debug & Diagnostics"])
async def debug_indexed_content_detailed():
    """Get detailed information about indexed content including sample text"""
    try:
        from app.services.search import get_indexed_topics_and_content
        content_info = get_indexed_topics_and_content()
        if content_info is None:
            raise QuizError.server_error("Failed to retrieve indexed content details")
        return content_info
    except QuizError:
        raise
    except Exception as e:
        log.error("debug.indexed_content_detailed.error", error=str(e))
        raise QuizError.server_error(f"Failed to retrieve indexed content details: {str(e)}")

# ---------- POST /quizzes/export/txt/last ----------
@router.post("/export/txt/last", response_model=ExportResponse, status_code=200, tags=["Quiz Export"])
async def export_last_quiz_to_txt(filename: str = None):
    """Export the most recently generated quiz to a TXT file"""
    global _last_generated_quiz
    
    if _last_generated_quiz is None:
        raise QuizError.not_found("No quiz has been generated yet. Generate a quiz first using /quizzes/generate")
    
    try:
        import os
        from datetime import datetime
        
        # Create filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = _last_generated_quiz["topic"].replace(' ', '_')
            filename = f"quiz_{safe_topic}_{timestamp}.txt"
        else:
            filename = filename if filename.endswith('.txt') else f"{filename}.txt"
        
        # Ensure safe filename
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '_', '-', '.')).strip()
        
        # Create exports directory if it doesn't exist
        exports_dir = os.path.join(os.getcwd(), "exports")
        os.makedirs(exports_dir, exist_ok=True)
        
        file_path = os.path.join(exports_dir, filename)
        
        # Create ExportRequest from stored quiz data
        export_req = ExportRequest(
            topic=_last_generated_quiz["topic"],
            difficulty=_last_generated_quiz["difficulty"],
            employee_level=_last_generated_quiz["employee_level"],
            num_questions=_last_generated_quiz["num_questions"],
            variants=_last_generated_quiz["result"]["variants"],
            filename=filename
        )
        
        # Generate TXT content
        content = generate_txt_content(export_req)
        
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        log.info("export.last_quiz.success", filename=filename, topic=_last_generated_quiz["topic"])
        
        return ExportResponse(
            filename=filename,
            file_path=file_path,
            message=f"Last generated quiz exported successfully to {filename}"
        )
        
    except Exception as e:
        log.error("export.last_quiz.failed", error=str(e))
        raise QuizError.server_error(f"Failed to export last quiz: {str(e)}")

# ---------- GET /quizzes/last ----------
@router.get("/last", tags=["Quiz Generation"])
async def get_last_quiz_info():
    """Get information about the most recently generated quiz"""
    global _last_generated_quiz
    
    if _last_generated_quiz is None:
        raise QuizError.not_found("No quiz has been generated yet")
    
    return {
        "topic": _last_generated_quiz["topic"],
        "num_questions": _last_generated_quiz["num_questions"],
        "difficulty": _last_generated_quiz["difficulty"],
        "employee_level": _last_generated_quiz["employee_level"],
        "num_variants": _last_generated_quiz["num_variants"],
        "available_for_export": True
    }

# ---------- POST /quizzes/export/txt ----------
@router.post("/export/txt", response_model=ExportResponse, status_code=200, tags=["Quiz Export"])
async def export_quiz_to_txt(req: ExportRequest):
    """Export quiz variants to a TXT file"""
    try:
        import os
        from datetime import datetime
        
        # Create filename if not provided
        if not req.filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"quiz_{req.topic.replace(' ', '_')}_{timestamp}.txt"
        else:
            filename = req.filename if req.filename.endswith('.txt') else f"{req.filename}.txt"
        
        # Ensure safe filename
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '_', '-', '.')).strip()
        
        # Create exports directory if it doesn't exist
        exports_dir = os.path.join(os.getcwd(), "exports")
        os.makedirs(exports_dir, exist_ok=True)
        
        file_path = os.path.join(exports_dir, filename)
        
        # Generate TXT content
        content = generate_txt_content(req)
        
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        log.info("export.txt.success", filename=filename, variants=len(req.variants))
        
        return ExportResponse(
            filename=filename,
            file_path=file_path,
            message=f"Quiz exported successfully to {filename}"
        )
        
    except Exception as e:
        log.error("export.txt.failed", error=str(e))
        raise QuizError.server_error(f"Failed to export quiz: {str(e)}")

def generate_txt_content(req: ExportRequest) -> str:
    """Generate formatted TXT content for quiz export"""
    content = []
    
    # Header
    content.append("="*60)
    content.append(f"QUIZ: {req.topic.upper()}")
    content.append(f"Difficulty: {req.difficulty}")
    content.append(f"Employee Level: {req.employee_level}")
    content.append(f"Number of Questions: {req.num_questions}")
    content.append(f"Number of Variants: {len(req.variants)}")
    content.append("="*60)
    content.append("")
    
    # Each variant
    for variant in req.variants:
        content.append(f"VARIANT {variant.variant_id}")
        content.append("-" * 20)
        content.append("")
        
        for i, question in enumerate(variant.questions, 1):
            content.append(f"Question {i}: {question.stem}")
            content.append("")
            
            # Options
            for j, option in enumerate(question.options):
                marker = "✓" if j == question.correct_index else " "
                content.append(f"  {chr(65+j)}) {option.text} {marker}")
            
            content.append("")
            
            # Explanation
            if question.explanation:
                content.append(f"Explanation: {question.explanation}")
                content.append("")
            
            # Source
            content.append(f"Source: {question.source}")
            content.append("")
            content.append("-" * 40)
            content.append("")
        
        content.append("")
        content.append("="*60)
        content.append("")
    
    return "\n".join(content)


# ---------- Additional Polling Endpoints ----------
@router.get("/api/v1/quizzes/poll/{job_id}", response_model=PollStatusResponse, tags=["Task Polling - Alternate Path"])
async def poll_task_status_v1(job_id: str):
    """Duplicate polling endpoint at /api/v1/quizzes/poll/{job_id} - works for PDF, folder, and article processing jobs"""
    # Delegate to the main polling function
    return await poll_task_status(job_id)


# ---------- Task Management ----------
@router.delete("/tasks/{job_id}", tags=["Task Management"])
async def delete_task(job_id: str):
    """Delete/cancel a background task by job ID"""
    try:
        res = AsyncResult(job_id)
        
        if res is None:
            raise QuizError.not_found(f"Task {job_id} not found")
        
        # Revoke the task if it's still pending or running
        if res.status in ['PENDING', 'STARTED']:
            res.revoke(terminate=True)
            log.info("task.deleted", job_id=job_id, status="cancelled")
            return {"job_id": job_id, "status": "cancelled", "message": "Task has been cancelled"}
        elif res.status == 'SUCCESS':
            log.info("task.delete_attempted", job_id=job_id, status="already_completed")
            return {"job_id": job_id, "status": "completed", "message": "Task was already completed and cannot be cancelled"}
        elif res.status == 'FAILURE':
            log.info("task.delete_attempted", job_id=job_id, status="already_failed")
            return {"job_id": job_id, "status": "failed", "message": "Task had already failed"}
        else:
            log.info("task.delete_attempted", job_id=job_id, status=res.status)
            return {"job_id": job_id, "status": res.status, "message": f"Task is in {res.status} state"}
            
    except AttributeError as e:
        if "DisabledBackend" in str(e):
            log.warning("task.delete.no_backend", job_id=job_id)
            raise QuizError.server_error("Task management not available - Redis backend disabled")
        else:
            log.error("task.delete.error", job_id=job_id, error=str(e))
            raise QuizError.server_error(f"Error deleting task: {str(e)}")
    except Exception as e:
        log.error("task.delete.error", job_id=job_id, error=str(e))
        raise QuizError.server_error(f"Error deleting task: {str(e)}")


@router.delete("/poll/{job_id}", tags=["Task Management"])
async def delete_task_alt(job_id: str):
    """Alternative delete endpoint for background tasks"""
    # Delegate to the main delete function
    return await delete_task(job_id)
