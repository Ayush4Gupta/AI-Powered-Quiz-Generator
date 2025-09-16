"""
Session management endpoints for quiz API.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid
import weaviate
import structlog
from typing import Dict, List, Any
from app.core.settings import get_settings

router = APIRouter(prefix="/api/sessions", tags=["Session Management"])
settings = get_settings()
log = structlog.get_logger()

def track_quiz_session_usage(session_id: str):
    """
    Track that a session has been used for quiz generation.
    Creates or updates a QuizSession object in Weaviate.
    """
    try:
        client = weaviate.Client(settings.weaviate_url)
        import time
        
        # Check if QuizSession class exists, if not create it
        try:
            schema = client.schema.get("QuizSession")
        except Exception:
            # Create QuizSession class schema
            quiz_session_schema = {
                "class": "QuizSession",
                "description": "Tracks sessions used for quiz generation",
                "properties": [
                    {
                        "name": "session_id",
                        "dataType": ["text"],
                        "description": "Unique session identifier"
                    },
                    {
                        "name": "last_used_timestamp",
                        "dataType": ["number"],
                        "description": "Timestamp when session was last used for quiz generation"
                    },
                    {
                        "name": "quiz_count",
                        "dataType": ["int"],
                        "description": "Number of quizzes generated in this session"
                    }
                ]
            }
            client.schema.create_class(quiz_session_schema)
            log.info("quiz_session.schema_created")
        
        # Check if session already exists
        existing = client.query.get("QuizSession", ["session_id", "quiz_count"]).with_where({
            "path": ["session_id"],
            "operator": "Equal",
            "valueText": session_id
        }).with_limit(1).do()
        
        current_time = int(time.time())
        
        if existing and "data" in existing and "Get" in existing["data"] and "QuizSession" in existing["data"]["Get"] and existing["data"]["Get"]["QuizSession"]:
            # Update existing session
            existing_session = existing["data"]["Get"]["QuizSession"][0]
            current_count = existing_session.get("quiz_count", 0)
            
            # Get the UUID of the existing object for update
            session_objects = client.data_object.get(class_name="QuizSession", where={
                "path": ["session_id"],
                "operator": "Equal",
                "valueText": session_id
            })
            
            if session_objects and "objects" in session_objects and session_objects["objects"]:
                object_uuid = session_objects["objects"][0]["id"]
                client.data_object.update(
                    uuid=object_uuid,
                    class_name="QuizSession",
                    data_object={
                        "last_used_timestamp": current_time,
                        "quiz_count": current_count + 1
                    }
                )
                log.info("quiz_session.updated", session_id=session_id, quiz_count=current_count + 1)
        else:
            # Create new session tracking
            client.data_object.create(
                data_object={
                    "session_id": session_id,
                    "last_used_timestamp": current_time,
                    "quiz_count": 1
                },
                class_name="QuizSession"
            )
            log.info("quiz_session.created", session_id=session_id)
            
    except Exception as e:
        log.error("quiz_session.track_failed", session_id=session_id, error=str(e))
        # Don't raise exception, as this is just tracking

class SessionResponse(BaseModel):
    session_id: str
    message: str

class SessionListResponse(BaseModel):
    sessions: List[Dict[str, Any]]
    total_count: int

@router.post("/create", response_model=SessionResponse)
async def create_session():
    """
    Create a new session ID for PDF upload and quiz generation.
    Each session isolates content completely from other sessions.
    """
    try:
        session_id = str(uuid.uuid4())
        log.info("session.created", session_id=session_id)
        
        return SessionResponse(
            session_id=session_id,
            message=f"Session {session_id} created successfully. Use this ID for PDF uploads and quiz generation."
        )
    except Exception as e:
        log.error("session.create_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@router.get("/list", response_model=SessionListResponse)
async def list_sessions():
    """
    List all sessions that have been used, including those with content and those used for quiz generation.
    """
    try:
        client = weaviate.Client(settings.weaviate_url)
        
        # Query all documents with session_id to get sessions with content
        result = client.query.get("DocumentChunk", ["session_id", "filename", "upload_timestamp"]).with_limit(1000).do()
        
        sessions_data = {}
        if result and "data" in result and "Get" in result["data"] and "DocumentChunk" in result["data"]["Get"]:
            for doc in result["data"]["Get"]["DocumentChunk"]:
                session_id = doc.get("session_id")
                if session_id:
                    if session_id not in sessions_data:
                        sessions_data[session_id] = {
                            "session_id": session_id,
                            "document_count": 0,
                            "filenames": set(),
                            "upload_timestamp": doc.get("upload_timestamp"),
                            "has_content": True,
                            "session_type": "content"
                        }
                    sessions_data[session_id]["document_count"] += 1
                    if doc.get("filename"):
                        sessions_data[session_id]["filenames"].add(doc.get("filename"))
        
        # Also check for sessions that have been used for quiz generation (stored in a simple tracking schema)
        try:
            # Try to query QuizSession objects if they exist
            quiz_result = client.query.get("QuizSession", ["session_id", "last_used_timestamp", "quiz_count"]).with_limit(1000).do()
            
            if quiz_result and "data" in quiz_result and "Get" in quiz_result["data"] and "QuizSession" in quiz_result["data"]["Get"]:
                for session in quiz_result["data"]["Get"]["QuizSession"]:
                    session_id = session.get("session_id")
                    if session_id and session_id not in sessions_data:
                        sessions_data[session_id] = {
                            "session_id": session_id,
                            "document_count": 0,
                            "filenames": [],
                            "upload_timestamp": None,
                            "last_used_timestamp": session.get("last_used_timestamp"),
                            "quiz_count": session.get("quiz_count", 0),
                            "has_content": False,
                            "session_type": "quiz_only"
                        }
                    elif session_id in sessions_data:
                        # Session has both content and quiz usage
                        sessions_data[session_id]["last_used_timestamp"] = session.get("last_used_timestamp")
                        sessions_data[session_id]["quiz_count"] = session.get("quiz_count", 0)
                        sessions_data[session_id]["session_type"] = "content_and_quiz"
        except Exception as e:
            # QuizSession schema might not exist yet, that's okay
            log.debug("session.list.no_quiz_tracking", error=str(e))
        
        # Convert to list and clean up filenames
        sessions_list = []
        for session_data in sessions_data.values():
            session_info = {
                "session_id": session_data["session_id"],
                "document_count": session_data["document_count"],
                "filenames": list(session_data["filenames"]) if isinstance(session_data["filenames"], set) else session_data["filenames"],
                "upload_timestamp": session_data["upload_timestamp"],
                "has_content": session_data.get("has_content", True),
                "session_type": session_data.get("session_type", "content")
            }
            
            # Add quiz-specific fields if available
            if "last_used_timestamp" in session_data:
                session_info["last_used_timestamp"] = session_data["last_used_timestamp"]
            if "quiz_count" in session_data:
                session_info["quiz_count"] = session_data["quiz_count"]
                
            sessions_list.append(session_info)
        
        log.info("session.list", total_sessions=len(sessions_list))
        
        return SessionListResponse(
            sessions=sessions_list,
            total_count=len(sessions_list)
        )
        
    except Exception as e:
        log.error("session.list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")

@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a session and all its associated content from the database.
    This removes both PDF content and quiz session tracking.
    """
    try:
        client = weaviate.Client(settings.weaviate_url)
        
        # Count documents before deletion for confirmation
        count_result = client.query.get("DocumentChunk", ["session_id"]).with_where({
            "path": ["session_id"],
            "operator": "Equal", 
            "valueText": session_id
        }).with_limit(1000).do()
        
        doc_count = 0
        if count_result and "data" in count_result and "Get" in count_result["data"] and "DocumentChunk" in count_result["data"]["Get"]:
            doc_count = len(count_result["data"]["Get"]["DocumentChunk"])
        
        # Check for quiz session tracking
        quiz_session_exists = False
        try:
            quiz_result = client.query.get("QuizSession", ["session_id"]).with_where({
                "path": ["session_id"],
                "operator": "Equal",
                "valueText": session_id
            }).with_limit(1).do()
            
            if quiz_result and "data" in quiz_result and "Get" in quiz_result["data"] and "QuizSession" in quiz_result["data"]["Get"] and quiz_result["data"]["Get"]["QuizSession"]:
                quiz_session_exists = True
        except Exception:
            pass  # QuizSession schema might not exist
        
        if doc_count == 0 and not quiz_session_exists:
            log.warning("session.delete_not_found", session_id=session_id)
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Delete all documents for this session
        if doc_count > 0:
            delete_result = client.batch.delete_objects(
                class_name="DocumentChunk",
                where={
                    "path": ["session_id"],
                    "operator": "Equal",
                    "valueText": session_id
                }
            )
            log.info("session.documents_deleted", session_id=session_id, documents_deleted=doc_count)
        
        # Delete quiz session tracking
        if quiz_session_exists:
            try:
                client.batch.delete_objects(
                    class_name="QuizSession",
                    where={
                        "path": ["session_id"],
                        "operator": "Equal",
                        "valueText": session_id
                    }
                )
                log.info("session.quiz_tracking_deleted", session_id=session_id)
            except Exception as e:
                log.warning("session.quiz_tracking_delete_failed", session_id=session_id, error=str(e))
        
        message = f"Session {session_id} deleted successfully."
        if doc_count > 0:
            message += f" Removed {doc_count} documents."
        if quiz_session_exists:
            message += " Removed quiz tracking."
        
        log.info("session.deleted", session_id=session_id, documents_deleted=doc_count, quiz_tracking_deleted=quiz_session_exists)
        
        return SessionResponse(
            session_id=session_id,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error("session.delete_failed", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

@router.get("/{session_id}/info")
async def get_session_info(session_id: str):
    """
    Get detailed information about a specific session.
    """
    try:
        client = weaviate.Client(settings.weaviate_url)
        
        # Get all documents for this session
        result = client.query.get("DocumentChunk", ["session_id", "filename", "upload_timestamp", "text"]).with_where({
            "path": ["session_id"],
            "operator": "Equal", 
            "valueText": session_id
        }).with_limit(1000).do()
        
        documents = []
        if result and "data" in result and "Get" in result["data"] and "DocumentChunk" in result["data"]["Get"]:
            documents = result["data"]["Get"]["DocumentChunk"]
        
        # Check for quiz session tracking
        quiz_session_data = None
        try:
            quiz_result = client.query.get("QuizSession", ["session_id", "last_used_timestamp", "quiz_count"]).with_where({
                "path": ["session_id"],
                "operator": "Equal",
                "valueText": session_id
            }).with_limit(1).do()
            
            if quiz_result and "data" in quiz_result and "Get" in quiz_result["data"] and "QuizSession" in quiz_result["data"]["Get"] and quiz_result["data"]["Get"]["QuizSession"]:
                quiz_session_data = quiz_result["data"]["Get"]["QuizSession"][0]
        except Exception:
            pass  # QuizSession schema might not exist
        
        # If neither documents nor quiz session exists, return 404
        if not documents and not quiz_session_data:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Analyze session content
        filenames = set()
        total_characters = 0
        upload_timestamps = set()
        
        for doc in documents:
            if doc.get("filename"):
                filenames.add(doc.get("filename"))
            if doc.get("text"):
                total_characters += len(doc.get("text"))
            if doc.get("upload_timestamp"):
                upload_timestamps.add(doc.get("upload_timestamp"))
        
        session_info = {
            "session_id": session_id,
            "document_count": len(documents),
            "filenames": list(filenames),
            "total_characters": total_characters,
            "upload_timestamps": list(upload_timestamps),
            "sample_content": documents[0].get("text", "")[:200] + "..." if documents else "",
            "has_content": len(documents) > 0
        }
        
        # Add quiz session information if available
        if quiz_session_data:
            session_info.update({
                "quiz_count": quiz_session_data.get("quiz_count", 0),
                "last_used_timestamp": quiz_session_data.get("last_used_timestamp"),
                "session_type": "content_and_quiz" if documents else "quiz_only"
            })
        else:
            session_info["session_type"] = "content_only" if documents else "unknown"
        
        log.info("session.info", session_id=session_id, document_count=len(documents), has_quiz_data=quiz_session_data is not None)
        
        return session_info
        
    except HTTPException:
        raise
    except Exception as e:
        log.error("session.info_failed", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get session info: {str(e)}")
