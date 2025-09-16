from typing import List, Optional, Union, Any
from pydantic import BaseModel, Field, field_validator
import uuid

class IngestRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Session ID to group PDF uploads. If not provided, a new session is created.")
    clear_previous: bool = Field(True, description="Whether to clear previous PDF content before uploading new content")

class IngestResponse(BaseModel):
    job_id: str
    session_id: str = Field(..., description="Session ID for this upload session")
    message: str = Field(..., description="Status message about the upload")

class GenerateRequest(BaseModel):
    topic: Optional[str] = Field(None, description="Topic for the quiz. If not provided or empty, generates quiz from all indexed content in the session.")
    num_questions: int = Field(..., ge=1, le=50)
    difficulty: str
    employee_level: str
    num_variants: int = Field(1, ge=1, le=10, description="Number of quiz variants to generate for different people")
    session_id: Optional[str] = Field(None, description="Session ID to use specific content. If not provided, uses general knowledge only.")
    use_all_content: bool = Field(False, description="If True, generates quiz from all indexed content in the session, ignoring the topic parameter.")
    # Removed use_latest_upload_only as it's always true in real scenarios

class Option(BaseModel):
    text: str

class Question(BaseModel):
    stem: str
    options: List[Option]
    correct_index: int
    explanation: Optional[str] = Field(None, description="Explanation for the correct answer")
    source: Optional[str] = Field(None, description="Source of the question: 'pdf' or 'general'")

class GenerateResponse(BaseModel):
    job_id: str

class QuizVariant(BaseModel):
    variant_id: int = Field(..., description="Unique identifier for this variant (1, 2, 3, etc.)")
    questions: List[Question]

class QuizResult(BaseModel):
    topic: str
    num_questions: int
    difficulty: str
    employee_level: str
    variants: List[QuizVariant] = Field(..., description="List of quiz variants for different people")

class ExportRequest(BaseModel):
    topic: str
    num_questions: int
    difficulty: str
    employee_level: str
    variants: List[QuizVariant]
    filename: Optional[str] = Field(None, description="Optional filename for the exported file")

class ExportResponse(BaseModel):
    filename: str
    file_path: str
    message: str

class PollStatusResponse(BaseModel):
    job_id: str
    status: str = Field(..., description="Status: processing, completed, failed, not_found")
    result: Optional[Any] = Field(None, description="Task result when completed, error message when failed")
    
    class Config:
        # Exclude fields with None values from the serialized output
        exclude_none = True
    
    def model_dump(self, **kwargs):
        """Custom serialization to completely omit result field when None"""
        data = super().model_dump(**kwargs)
        # Remove result field if it's None or empty
        if 'result' in data and (data['result'] is None or data['result'] == ""):
            del data['result']
        return data

# Document processing schemas
class DocumentMetadata(BaseModel):
    source: str = Field(..., description="File path or source identifier")
    file_type: Optional[str] = Field(None, description="File type/extension")
    file_size: Optional[int] = Field(None, description="File size in bytes")

class ExtractedDocument(BaseModel):
    content: str = Field(..., description="Extracted plain text content")
    metadata: DocumentMetadata = Field(..., description="Document metadata")

class FolderExtractionRequest(BaseModel):
    folder_path: str = Field(..., description="Path to folder containing documents")
    session_id: Optional[str] = Field(None, description="Session ID for content grouping")
    clear_previous: bool = Field(True, description="Whether to clear previous content in session")
    recursive: bool = Field(True, description="Whether to search subfolders recursively")

class FolderExtractionResponse(BaseModel):
    job_id: str = Field(..., description="Background task ID for tracking progress")
    session_id: str = Field(..., description="Session ID where documents will be stored")
    message: str = Field(..., description="Status message")
    files_found: int = Field(..., description="Number of supported files found")
    supported_types: List[str] = Field(..., description="List of supported file extensions")

# Article processing options
class ProcessingOptions(BaseModel):
    max_articles: int = Field(10, ge=1, le=20, description="Maximum number of articles to process")
    timeout_per_article: int = Field(30, ge=10, le=60, description="Timeout in seconds per article")
    respect_delays: bool = Field(True, description="Add delays between requests to be respectful")

# Article ingestion schemas (separate from quiz generation)
class ArticleSource(BaseModel):
    url: str = Field(..., pattern=r'^https?://.+', description="Article URL (must be http/https)")
    title: Optional[str] = Field(None, description="Optional title for reference")
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

class ArticleIngestionRequest(BaseModel):
    articles: List[ArticleSource] = Field(..., min_items=1, max_items=20, description="List of article URLs to ingest")
    session_id: Optional[str] = Field(None, description="Session ID to group article uploads. If not provided, a new session is created.")
    clear_previous: bool = Field(True, description="Whether to clear previous content before uploading new articles")
    processing_options: Optional[ProcessingOptions] = Field(default_factory=ProcessingOptions, description="Article processing options")

class ArticleIngestionResponse(BaseModel):
    job_id: str = Field(..., description="Background task ID for tracking progress")
    session_id: str = Field(..., description="Session ID for this upload session")
    message: str = Field(..., description="Status message about the upload")
    articles_to_process: int = Field(..., description="Number of articles queued for processing")
