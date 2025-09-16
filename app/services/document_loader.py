# document_loader.py
"""
Document loading service for folder-based extraction.
Integrates with existing session and chunking system.
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
import structlog
from app.utils.document_extractors import (
    extract_text_from_file, 
    get_supported_extensions, 
    is_supported_file,
    DocumentExtractionError
)
from app.schemas.quizzes import ExtractedDocument, DocumentMetadata

log = structlog.get_logger()

class DocumentLoader:
    """Document loader that processes folders and extracts text from multiple file types"""
    
    def __init__(self):
        self.supported_extensions = get_supported_extensions()
    
    def scan_folder(self, folder_path: str, recursive: bool = True) -> List[Path]:
        """
        Scan folder for supported documents
        
        Args:
            folder_path: Path to folder to scan
            recursive: Whether to scan subfolders
            
        Returns:
            List of supported file paths
        """
        folder = Path(folder_path)
        
        if not folder.exists():
            raise ValueError(f"Folder does not exist: {folder_path}")
        
        if not folder.is_dir():
            raise ValueError(f"Path is not a directory: {folder_path}")
        
        supported_files = []
        
        if recursive:
            # Use glob pattern to find all files recursively
            for ext in self.supported_extensions:
                pattern = f"**/*{ext}"
                supported_files.extend(folder.glob(pattern))
        else:
            # Only scan immediate directory
            for file_path in folder.iterdir():
                if file_path.is_file() and is_supported_file(file_path):
                    supported_files.append(file_path)
        
        log.info("document_loader.scan_completed", 
                folder_path=folder_path, 
                recursive=recursive,
                files_found=len(supported_files),
                supported_extensions=self.supported_extensions)
        
        return supported_files
    
    def extract_from_files(self, file_paths: List[Path]) -> List[ExtractedDocument]:
        """
        Extract text from list of files
        
        Args:
            file_paths: List of file paths to process
            
        Returns:
            List of ExtractedDocument objects
        """
        documents = []
        success_count = 0
        error_count = 0
        
        for file_path in file_paths:
            try:
                log.info("document_loader.processing_file", file_path=str(file_path))
                
                # Extract text content
                content = extract_text_from_file(file_path)
                
                # Get file metadata
                file_stat = file_path.stat()
                metadata = DocumentMetadata(
                    source=str(file_path),
                    file_type=file_path.suffix.lower(),
                    file_size=file_stat.st_size
                )
                
                # Create document object
                document = ExtractedDocument(
                    content=content,
                    metadata=metadata
                )
                
                documents.append(document)
                success_count += 1
                
                log.info("document_loader.file_processed", 
                        file_path=str(file_path),
                        content_length=len(content),
                        file_size=file_stat.st_size)
                
            except DocumentExtractionError as e:
                error_count += 1
                log.error("document_loader.extraction_failed", 
                         file_path=str(file_path), 
                         error=str(e))
            except Exception as e:
                error_count += 1
                log.error("document_loader.unexpected_error", 
                         file_path=str(file_path), 
                         error=str(e))
        
        log.info("document_loader.extraction_completed",
                total_files=len(file_paths),
                successful=success_count,
                failed=error_count)
        
        return documents
    
    def load_documents_from_folder(self, folder_path: str, recursive: bool = True) -> List[ExtractedDocument]:
        """
        Complete workflow: scan folder and extract documents
        
        Args:
            folder_path: Path to folder containing documents
            recursive: Whether to scan subfolders
            
        Returns:
            List of ExtractedDocument objects
        """
        # Scan folder for supported files
        file_paths = self.scan_folder(folder_path, recursive)
        
        if not file_paths:
            log.warning("document_loader.no_files_found", 
                       folder_path=folder_path,
                       supported_extensions=self.supported_extensions)
            return []
        
        # Extract text from all files
        documents = self.extract_from_files(file_paths)
        
        return documents

# Global instance for use in API endpoints
document_loader = DocumentLoader()
