# settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    # API
    app_name: str = "Quiz Generator"
    api_prefix: str = "/api/v1"
    
    # External services - prioritize environment variables
    weaviate_url: str = os.getenv('WEAVIATE_URL', 'http://localhost:8080')
    cohere_api_key: str = os.getenv('COHERE_API_KEY', '')
    groq_api_key: str = os.getenv('GROQ_API_KEY', '')
    
    # Embeddings
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Celery / Redis - prioritize environment variables
    celery_broker_url: str = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    celery_result_backend: str = os.getenv('CELERY_RESULT_BACKEND', os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'))
    
    # Limits
    max_questions: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
