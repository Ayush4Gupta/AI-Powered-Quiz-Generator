# Quiz Generator Application

A sophisticated AI-powered quiz generation system that creates multiple-choice questions from uploaded PDF documents using advanced retrieval and generation techniques.

## 🏗️ Project Structure

```
quiz/
├── app/                          # Main application code
│   ├── __init__.py
│   ├── main.py                   # FastAPI application entry point
│   ├── worker.py                 # Celery worker configuration
│   ├── worker_manager.py         # Celery worker management
│   │
│   ├── api/                      # API route handlers
│   │   ├── quizzes.py           # Quiz generation and PDF ingestion endpoints
│   │   └── sessions.py          # Session management endpoints
│   │
│   ├── background/               # Background task processing
│   │   └── tasks.py             # Celery tasks for PDF processing
│   │
│   ├── core/                     # Core application components
│   │   ├── auth.py              # Authentication (placeholder)
│   │   ├── errors.py            # Custom error handling
│   │   ├── logging.py           # Structured logging configuration
│   │   ├── rate_limit.py        # Rate limiting middleware
│   │   ├── settings.py          # Application settings and configuration
│   │   └── telemetry.py         # OpenTelemetry monitoring
│   │
│   ├── models/                   # Data models and schemas
│   │   └── weaviate_schema.py   # Vector database schema definitions
│   │
│   ├── schemas/                  # API request/response models
│   │   └── quizzes.py           # Pydantic models for quiz API
│   │
│   ├── services/                 # Business logic services
│   │   ├── ingestion.py         # PDF upload and processing
│   │   ├── offline_quiz_fallback.py  # Offline quiz generation
│   │   ├── quiz_generation.py   # Core quiz generation logic
│   │   └── search.py            # Semantic search and retrieval
│   │
│   └── utils/                    # Utility functions
│       ├── embeddings.py        # Text embedding utilities
│       ├── pdf.py               # PDF parsing utilities
│       └── splitters.py         # Text chunking strategies
│
├── exports/                      # Quiz export files
├── tests/                        # Test suite
├── uploads/                      # Uploaded PDF files
├── docker-compose.yml           # Docker services configuration
├── Dockerfile                   # Application container
├── requirements.txt             # Python dependencies
└── *.bat                       # Windows startup scripts
```

## 🚀 Technologies Used

### **Core Framework**
- **FastAPI** - Modern, fast web framework for building APIs
- **Uvicorn** - ASGI server for running FastAPI applications
- **Pydantic** - Data validation and settings management

### **AI & Machine Learning**
- **Deepseek R1** - Large Language Model for quiz question generation
- **Sentence Transformers** - Text embeddings (all-MiniLM-L6-v2)
- **Cohere** - Text reranking and synthetic document generation (HyDE)
- **LangChain** - AI application framework and utilities

### **Vector Database & Search**
- **Weaviate** - Vector database for semantic search
- **Hybrid Search** - Combines vector similarity and keyword matching
- **BM25** - Traditional keyword search as fallback

### **Background Processing**
- **Celery** - Distributed task queue for background processing
- **Redis** - Message broker and result backend for Celery

### **Document Processing**
- **PyPDF** - PDF parsing and text extraction
- **Text Chunking** - Intelligent document segmentation

### **Monitoring & Observability**
- **Structlog** - Structured logging with contextual information
- **OpenTelemetry** - Distributed tracing and metrics collection
- **Prometheus** - Application metrics and performance monitoring
- **Prometheus FastAPI Instrumentator** - Automatic API metrics collection

### **Development & Deployment**
- **Docker** - Containerization for consistent deployments
- **Docker Compose** - Multi-service orchestration and development environment

## 🧠 Core Approaches & Algorithms

### **1. Retrieval-Augmented Generation (RAG)**

The application implements a sophisticated RAG pipeline:

#### **Document Ingestion Pipeline**
```
PDF Upload → Text Extraction → Chunking → Embedding → Vector Storage
     ↓              ↓             ↓          ↓           ↓
   PyPDF      Clean & Parse   Intelligent  Sentence    Weaviate
              Remove noise    Splitting    Transformers Database
```

#### **Chunking Strategy**
- **Semantic Chunking**: Preserves meaning by splitting at natural boundaries
- **Overlap Management**: Prevents context loss between chunks
- **Size Optimization**: Balances context length with embedding quality

#### **Session-Based Isolation**
- Each PDF upload creates a unique session
- Questions are generated only from content within the same session
- Prevents cross-contamination between different document sets

### **2. Hybrid Search Architecture**

The search system combines multiple retrieval strategies:

```
User Query → Cleaned Topic → Multi-Strategy Search → Reranking → Results
                ↓
        ┌─────────────────┐
        │   Strategy 1    │ Hybrid Search (Vector + Keyword)
        │   Strategy 2    │ HyDE Vector Search  
        │   Strategy 3    │ BM25 Fallback
        └─────────────────┘
                ↓
        Result Deduplication → Cohere Reranking → Top-K Results
```

#### **Strategy 1: Hybrid Search**
- **Alpha Parameter**: 0.5 (equal weight to vector and keyword search)
- **Vector Component**: Semantic similarity using embeddings
- **Keyword Component**: Traditional BM25 text matching
- **Target**: Search within document TEXT content, not metadata

#### **Strategy 2: HyDE (Hypothetical Document Embeddings)**
- **Concept**: Generate synthetic document from query
- **Process**: Use Cohere to expand query into detailed paragraph
- **Benefit**: Bridge vocabulary gap between query and documents
- **Embedding**: Convert synthetic document to vector for similarity search

#### **Strategy 3: BM25 Fallback**
- **Trigger**: When hybrid and vector search return no results
- **Purpose**: Ensure we always return something relevant
- **Algorithm**: Traditional keyword-based information retrieval

#### **Reranking with Cohere**
- **Purpose**: Improve result quality and relevance ordering
- **Method**: Neural reranking of combined search results
- **Fallback**: Return results without reranking if Cohere unavailable

### **3. Intelligent Quiz Generation**

#### **Variant-Aware Generation**
```
Quiz Request → Variant Strategy → Content Selection → LLM Generation → Post-Processing
      ↓              ↓                ↓                 ↓              ↓
  Multi-variant   PDF vs General   Retrieval from    Deepseek R1    JSON Validation
  Configuration   Source Ratio     Session Content   Generation     Error Recovery
```

#### **Source Diversification Strategy**
- **Odd Variants** (1, 3, 5...): 80% PDF content, 20% general knowledge
- **Even Variants** (2, 4, 6...): 60% PDF content, 40% general knowledge
- **Purpose**: Create diverse question sets from same source material
- **Benefit**: Prevents repetitive questions across variants

#### **Content Selection Logic**
1. **Session-Based Retrieval**: Get relevant passages from uploaded PDFs
2. **Semantic Search**: Use hybrid search to find most relevant content
3. **Context Assembly**: Combine passages for optimal LLM input
4. **Fallback Strategy**: Use general knowledge when PDF content insufficient

#### **LLM Prompt Engineering**
- **Structured Prompts**: Detailed instructions for consistent output
- **Source Attribution**: Each question labeled with content source
- **Quality Controls**: Enforce answer distribution and explanation quality
- **JSON Schema**: Strict format requirements for reliable parsing

### **4. Error Handling & Reliability**

#### **Network Resilience**
- **Connectivity Checks**: DNS resolution tests before API calls
- **Graceful Degradation**: Offline fallbacks when external APIs unavailable
- **Retry Logic**: Exponential backoff for rate-limited API calls

#### **Offline Quiz Generation**
- **Trigger**: Network unavailable or API failures
- **Strategy**: Use pre-built question templates
- **Quality**: Basic questions based on topic keywords
- **User Experience**: Transparent fallback with clear messaging

#### **Background Processing**
- **Async PDF Processing**: Non-blocking document ingestion
- **Task Monitoring**: Real-time status updates for long-running tasks
- **Failure Recovery**: Automatic retries with exponential backoff
- **Resource Management**: Worker process isolation and cleanup

## 🔄 Application Workflow

### **1. PDF Upload & Processing**
```
1. User uploads PDF via /api/v1/quizzes/ingest
2. File validation (size, format, content)
3. Session creation or reuse
4. Background task queued for processing
5. PDF text extraction and cleaning
6. Intelligent text chunking
7. Embedding generation for each chunk
8. Vector storage in Weaviate with session metadata
9. Status updates via polling endpoint
```

### **2. Quiz Generation**
```
1. User requests quiz via /api/v1/quizzes/generate
2. Session validation and content availability check
3. Topic-based semantic search within session content
4. Multi-strategy retrieval (Hybrid + HyDE + BM25)
5. Content ranking and selection
6. Variant-specific source ratio application
7. LLM prompt construction with retrieved context
8. Deepseek R1 API call with retry logic
9. Response parsing and validation
10. Quiz variants assembly and return
```

### **3. Session Management**
```
1. Session creation for content isolation
2. Content tracking across uploads
3. Quiz generation history and analytics
4. Session cleanup and deletion
5. Cross-session content prevention
6. Usage statistics and reporting
```

### **4. Advanced Features**

#### **Multi-Variant Quiz Generation**
- **Intelligent Diversification**: Different source ratios per variant
- **Content Rotation**: Prevents question repetition across variants
- **Difficulty Scaling**: Adaptive question complexity
- **Source Attribution**: Clear marking of PDF vs general knowledge questions

#### **Semantic Search Pipeline**
- **Query Preprocessing**: Topic cleaning and normalization
- **Multi-Strategy Retrieval**: Parallel search execution with fallbacks
- **Result Fusion**: Intelligent combination of search results
- **Quality Ranking**: Neural reranking for optimal relevance

#### **Content Processing Pipeline**
- **PDF Text Extraction**: Robust parsing with error handling
- **Text Cleaning**: Noise removal and formatting normalization
- **Semantic Chunking**: Context-aware text segmentation
- **Embedding Generation**: High-quality vector representations
- **Metadata Enrichment**: Session and document tracking

## 🏃‍♂️ Getting Started

### **Prerequisites**
- Python 3.11+
- Docker & Docker Compose
- Redis server
- Weaviate vector database

### **Environment Setup**
```bash
# Clone repository
git clone <repository-url>
cd quiz

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys and service URLs
```

### **Required Environment Variables**
```env
# API Keys
COHERE_API_KEY=your_cohere_api_key
GROQ_API_KEY=your_groq_api_key

# Services
WEAVIATE_URL=http://localhost:8080
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### **Quick Start Options**

#### **Option 1: Docker Compose (Recommended)**
```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f app
```

#### **Option 2: Manual Setup**
```bash
# Start dependencies
docker-compose up -d redis weaviate

# Start application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start worker (separate terminal)
python -m celery -A app.worker worker --loglevel=info
```

#### **Option 3: Windows Batch Scripts**
```bash
# All-in-one startup
start-dev.bat

# Or separately
run_server.bat    # Start FastAPI server
start-worker.bat  # Start Celery worker
```

## 📚 API Documentation

### **Core Endpoints**

#### **System Health & Monitoring**
- `GET /livez` - Liveness probe (always returns 200 if app running)
- `GET /readyz` - Readiness probe (includes Celery worker health check)
- `GET /metrics` - Prometheus metrics endpoint

#### **Quiz Generation**
- `POST /api/v1/quizzes/generate` - Generate quiz questions with multiple variants
- `GET /api/v1/quizzes/last` - Get information about the last generated quiz

#### **Quiz Export**
- `POST /api/v1/quizzes/export/txt` - Export quiz to text format
- `POST /api/v1/quizzes/export/txt/last` - Export last generated quiz to text

#### **PDF Document Management**
- `POST /api/v1/quizzes/ingest` - Upload and process PDF documents
- `GET /api/v1/quizzes/pdf/{job_id}` - Poll PDF processing status

#### **Debug & Diagnostics**
- `GET /api/v1/quizzes/debug/indexed-content` - View indexed document statistics
- `GET /api/v1/quizzes/debug/indexed-content-detailed` - Detailed content analysis
- `GET /api/v1/quizzes/debug/search/{topic}` - Test search functionality for specific topic
- `GET /api/v1/quizzes/debug/search-detailed/{topic}` - Comprehensive search diagnostics

#### **Session Management**
- `POST /api/v1/api/sessions/create` - Create new content isolation session
- `GET /api/v1/api/sessions/list` - List all sessions with metadata
- `GET /api/v1/api/sessions/{session_id}/info` - Get detailed session information
- `DELETE /api/v1/api/sessions/{session_id}` - Delete session and all content

#### **API Documentation**
- `GET /api/v1/docs` - Interactive Swagger/OpenAPI documentation
- `GET /api/v1/redoc` - Alternative ReDoc documentation

### **Detailed API Reference**

#### **POST /api/v1/quizzes/generate**
Generate quiz questions from uploaded PDF content and general knowledge.

**Request Body:**
```json
{
  "topic": "machine learning algorithms",           // Required: Quiz topic
  "num_questions": 10,                             // Required: Number of questions (1-50)
  "difficulty": "intermediate",                    // Required: easy, intermediate, hard
  "employee_level": "senior",                      // Required: junior, mid, senior, expert
  "num_variants": 2,                              // Optional: Number of quiz variants (1-5)
  "session_id": "uuid-session-identifier"         // Optional: Content session filter
}
```

**Response:**
```json
{
  "variants": [
    {
      "variant_number": 1,
      "questions": [
        {
          "stem": "What is the primary purpose of backpropagation?",
          "options": [
            {"text": "Forward data flow"},
            {"text": "Calculate gradients for weight updates"},
            {"text": "Initialize network weights"},
            {"text": "Activate neurons"}
          ],
          "correct_index": 1,
          "explanation": "Backpropagation calculates gradients...",
          "source": "pdf"
        }
      ]
    }
  ],
  "metadata": {
    "topic": "machine learning algorithms",
    "total_questions": 10,
    "generated_at": "2025-07-22T10:30:00Z",
    "content_sources": ["pdf", "general"]
  }
}
```

#### **POST /api/v1/quizzes/ingest**
Upload and process PDF documents for quiz generation.

**Request (Multipart Form):**
```bash
Content-Type: multipart/form-data
- pdf: [PDF file] (required, max 50MB)
- session_id: [string] (optional, creates new if not provided)
- clear_previous: [boolean] (optional, default true)
```

**Response:**
```json
{
  "job_id": "uuid-task-identifier",
  "session_id": "uuid-session-identifier", 
  "message": "PDF upload started. Use the poll endpoint to check status."
}
```

#### **GET /api/v1/quizzes/pdf/{job_id}**
Poll the status of PDF processing job.

**Response States:**
```json
// Pending
{
  "job_id": "uuid-task-identifier",
  "status": "pending"
}

// Processing
{
  "job_id": "uuid-task-identifier", 
  "status": "processing"
}

// Completed
{
  "job_id": "uuid-task-identifier",
  "status": "completed",
  "result": "Successfully processed PDF: 45 chunks indexed"
}

// Failed
{
  "job_id": "uuid-task-identifier",
  "status": "failed",
  "result": "Error message describing failure"
}
```

#### **GET /api/v1/sessions/list**
List all content sessions with usage statistics.

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "uuid-identifier",
      "document_count": 45,
      "filenames": ["document1.pdf", "document2.pdf"],
      "upload_timestamp": 1642781234,
      "has_content": true,
      "session_type": "content_and_quiz",
      "quiz_count": 3,
      "last_used_timestamp": 1642781890
    }
  ],
  "total_count": 1
}
```

#### **GET /readyz**
Comprehensive readiness check including all dependencies.

**Response:**
```json
{
  "status": "ready",
  "celery_worker": "healthy",
  "api_prefix": "/api/v1"
}
```

### **Request Examples**

#### **Upload PDF with Session Management**
```bash
# Create new session
curl -X POST "http://localhost:8000/api/v1/sessions/create"

# Upload PDF to specific session
curl -X POST "http://localhost:8000/api/v1/quizzes/ingest" \
  -F "pdf=@machine_learning_guide.pdf" \
  -F "session_id=your-session-id-here" \
  -F "clear_previous=false"

# Check processing status
curl "http://localhost:8000/api/v1/quizzes/pdf/your-job-id-here"
```

#### **Generate Multi-Variant Quiz**
```bash
curl -X POST "http://localhost:8000/api/v1/quizzes/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "neural networks and deep learning",
    "num_questions": 15,
    "difficulty": "intermediate", 
    "employee_level": "senior",
    "num_variants": 3,
    "session_id": "your-session-id-here"
  }'
```

#### **Debug Search Performance**
```bash
# Test search functionality
curl "http://localhost:8000/api/v1/quizzes/debug/search/machine%20learning?session_id=your-session-id"

# Detailed search diagnostics
curl "http://localhost:8000/api/v1/quizzes/debug/search-detailed/neural%20networks"
```

#### **Export Generated Quiz**
```bash
# Export as JSON
curl "http://localhost:8000/api/v1/quizzes/export/json" > quiz.json

# Export as text file
curl "http://localhost:8000/api/v1/quizzes/export/txt" > quiz.txt
```

### **Error Handling**

#### **Standard Error Response**
```json
{
  "detail": "Human-readable error message"
}
```

#### **Common HTTP Status Codes**
- `200` - Success
- `400` - Bad Request (validation errors, file too large)
- `404` - Not Found (session/job not found)
- `422` - Unprocessable Entity (invalid request format)
- `429` - Too Many Requests (rate limiting)
- `500` - Internal Server Error
- `503` - Service Unavailable (dependencies down)

#### **Rate Limiting**
- **Quiz Generation**: 10 requests per minute per IP
- **PDF Upload**: 5 requests per minute per IP
- **Debug Endpoints**: 20 requests per minute per IP
- **Headers**: `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## � Monitoring & Metrics

### **Prometheus Integration**

The application automatically exposes comprehensive metrics via Prometheus FastAPI Instrumentator.

#### **Available Metrics Endpoint**
```
GET /metrics
```

#### **Key Metrics Collected**

##### **HTTP Request Metrics**
```prometheus
# Request count by method, endpoint, and status
http_requests_total{method="POST", handler="/api/v1/quizzes/generate", status="200"}

# Request duration histogram
http_request_duration_seconds{method="POST", handler="/api/v1/quizzes/generate"}

# Request size histogram
http_request_size_bytes{method="POST", handler="/api/v1/quizzes/ingest"}

# Response size histogram  
http_response_size_bytes{method="GET", handler="/api/v1/sessions/list"}

# Currently in-progress requests
http_requests_inprogress{method="POST", handler="/api/v1/quizzes/generate"}
```

##### **Application-Specific Metrics**
```prometheus
# Quiz generation success/failure rates
quiz_generation_total{status="success|failure", variant_count="1|2|3"}

# PDF processing metrics
pdf_processing_duration_seconds{status="success|failure"}
pdf_chunks_created_total{session_id="uuid"}

# Search performance metrics
search_strategy_used_total{strategy="hybrid|hyde|bm25"}
search_results_returned_total{strategy="hybrid|hyde|bm25"}

# Background task metrics
celery_task_duration_seconds{task_name="ingest_pdf", status="success|failure"}
celery_worker_health{worker_id="worker-1", status="healthy|unhealthy"}

# Session usage metrics
active_sessions_total
content_chunks_total{session_id="uuid"}
```

#### **Grafana Dashboard Configuration**

**Sample Dashboard Panels:**

1. **API Performance Panel**
```json
{
  "title": "Quiz API Request Rate",
  "target": "rate(http_requests_total{handler=~\"/api/v1/quizzes.*\"}[5m])",
  "type": "graph"
}
```

2. **Quiz Generation Success Rate**
```json
{
  "title": "Quiz Generation Success Rate",
  "target": "rate(quiz_generation_total{status=\"success\"}[5m]) / rate(quiz_generation_total[5m]) * 100",
  "type": "stat",
  "unit": "percent"
}
```

3. **PDF Processing Performance**
```json
{
  "title": "PDF Processing Duration",
  "target": "histogram_quantile(0.95, rate(pdf_processing_duration_seconds_bucket[5m]))",
  "type": "graph"
}
```

#### **Alert Rules**

**High Error Rate Alert:**
```yaml
groups:
  - name: quiz_api_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors per second"
```

**Worker Health Alert:**
```yaml
      - alert: CeleryWorkerDown
        expr: up{job="celery_worker"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Celery worker is down"
          description: "Background task processing is unavailable"
```

#### **Custom Metrics Implementation**

The application includes custom business metrics:

```python
# Example custom metrics in the codebase
from prometheus_client import Counter, Histogram, Gauge

# Quiz generation metrics
quiz_requests = Counter('quiz_generation_requests_total', 
                       'Total quiz generation requests', 
                       ['topic', 'difficulty', 'status'])

# PDF processing metrics  
pdf_processing_time = Histogram('pdf_processing_seconds',
                               'Time spent processing PDFs',
                               ['session_id', 'file_size_mb'])

# Active sessions gauge
active_sessions = Gauge('active_sessions_current',
                       'Number of active content sessions')
```

### **Structured Logging with Contextual Information**

#### **Log Format**
```json
{
  "timestamp": "2025-07-22T10:30:45.123Z",
  "level": "info",
  "event": "quiz.generation.completed",
  "topic": "machine learning",
  "num_questions": 10,
  "num_variants": 2,
  "session_id": "uuid-identifier",
  "processing_time_ms": 15420,
  "content_sources": ["pdf", "general"],
  "pdf_chunks_used": 8
}
```

#### **Key Log Events**
- `quiz.generation.started` - Quiz generation initiated
- `quiz.generation.completed` - Successful completion
- `quiz.generation.failed` - Generation failures with error context
- `pdf.ingestion.started` - PDF upload processing begins
- `pdf.ingestion.completed` - Processing finished with chunk count
- `search.strategy.executed` - Search strategy performance
- `celery.task.enqueued` - Background task queued
- `session.created` - New content session established

#### **Log Aggregation**

**ELK Stack Integration:**
```yaml
# Logstash configuration
input {
  beats {
    port => 5044
  }
}

filter {
  if [fields][service] == "quiz-api" {
    json {
      source => "message"
    }
    
    # Extract metrics from logs
    if [event] == "quiz.generation.completed" {
      metrics {
        meter => "quiz.generation.rate"
        add_tag => "metric"
      }
    }
  }
}
```

### **Health Monitoring**

#### **Readiness Probe Details**
The `/readyz` endpoint performs comprehensive health checks:

```python
async def readiness():
    checks = {
        "celery_worker": worker_manager.is_healthy(),
        "weaviate": check_weaviate_connection(),
        "redis": check_redis_connection(),
        "external_apis": check_api_connectivity()
    }
    
    all_healthy = all(checks.values())
    
    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }
```

#### **Dependency Health Checks**
- **Weaviate Vector Database**: Connection and schema validation
- **Redis Message Broker**: Connectivity and command execution
- **Celery Workers**: Task processing capability and queue depth
- **External APIs**: Deepseek, Cohere, Groq connectivity tests
- **File System**: Upload directory accessibility and disk space

#### **Monitoring Integration Examples**

**Kubernetes Liveness/Readiness:**
```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: quiz-api
    livenessProbe:
      httpGet:
        path: /livez
        port: 8000
      initialDelaySeconds: 30
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 5
```

**Docker Compose Health Check:**
```yaml
services:
  app:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/readyz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## �🔧 Configuration

### **Application Settings**
Located in `app/core/settings.py`:

- **API Configuration**: Prefix, title, documentation URLs
- **External Services**: Weaviate, Cohere, Groq API endpoints
- **Embedding Model**: Configurable sentence transformer model
- **Rate Limits**: Request throttling and quotas
- **Processing Limits**: Maximum questions, file sizes, timeouts

### **Vector Database Schema**
- **DocumentChunk**: Stores PDF content with embeddings
- **QuizSession**: Tracks quiz generation usage
- **Session Isolation**: Prevents cross-session content leakage

## 🧪 Testing

The project includes comprehensive tests covering:

- **API Endpoints**: Request validation, response formats
- **Background Tasks**: PDF processing, task status
- **Search Functionality**: Retrieval accuracy, ranking quality
- **Quiz Generation**: Output validation, variant diversity
- **Error Handling**: Network failures, malformed inputs
- **Integration Tests**: End-to-end workflows

```bash
# Run test suite
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_api_health_check.py
python -m pytest tests/test_quiz_export_functionality.py
```

## 🏗️ Architecture Patterns

### **Microservices Design**
- **Service Separation**: API, worker, database layers
- **Async Processing**: Background tasks for long operations
- **Stateless API**: Session state stored externally
- **Health Monitoring**: Comprehensive readiness checks

### **Data Flow Architecture**
```
Client → API Gateway → Business Logic → Background Tasks
   ↓         ↓             ↓               ↓
   ↓    Rate Limiting  Session Mgmt   PDF Processing
   ↓    Error Handling Content Search  Vector Storage
   ↓    Telemetry     Quiz Generation  Result Tracking
```

### **Scalability Considerations**
- **Horizontal Scaling**: Multiple worker processes for background tasks
- **Caching**: Redis for task results and session data
- **Database Partitioning**: Session-based content isolation prevents resource conflicts
- **Resource Management**: Configurable concurrency limits and memory usage
- **Load Balancing**: Stateless API design supports multiple instances

### **Performance Optimization**
- **Vector Search Optimization**: Efficient embedding storage and retrieval
- **Chunking Strategy**: Optimal text segmentation for embedding quality
- **Connection Pooling**: Persistent connections to databases and external APIs
- **Async Processing**: Non-blocking I/O for improved throughput
- **Memory Management**: Efficient handling of large PDF documents

## 🚀 Deployment

### **Production Deployment Options**

#### **Docker Compose Production**
```bash
# Production environment
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# With custom environment
ENV=production docker-compose up -d
```

#### **Kubernetes Deployment**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: quiz-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: quiz-api
  template:
    metadata:
      labels:
        app: quiz-api
    spec:
      containers:
      - name: quiz-api
        image: quiz-generator:latest
        ports:
        - containerPort: 8000
        env:
        - name: WEAVIATE_URL
          value: "http://weaviate-service:8080"
        - name: CELERY_BROKER_URL
          value: "redis://redis-service:6379/0"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

#### **Environment Variables for Production**
```env
# Production API Keys
COHERE_API_KEY=prod_cohere_key
GROQ_API_KEY=prod_groq_key

# Production Services
WEAVIATE_URL=https://prod-weaviate.example.com
CELERY_BROKER_URL=redis://prod-redis.example.com:6379/0

# Performance Tuning
WORKER_CONCURRENCY=4
MAX_QUESTIONS_PER_REQUEST=25
EMBEDDING_BATCH_SIZE=100

# Security
ALLOWED_ORIGINS=https://quiz-frontend.example.com
RATE_LIMIT_ENABLED=true
API_KEY_REQUIRED=true
```

### **Infrastructure Requirements**

#### **Minimum System Requirements**
- **CPU**: 2 cores (4 recommended)
- **RAM**: 4GB (8GB recommended)
- **Disk**: 20GB SSD (for uploads and vector storage)
- **Network**: Stable internet for external API calls

#### **Recommended Production Setup**
- **API Server**: 2-4 instances behind load balancer
- **Celery Workers**: 2-6 workers depending on PDF volume
- **Weaviate**: Dedicated instance with SSD storage
- **Redis**: Persistent storage with backup
- **Monitoring**: Prometheus + Grafana + AlertManager

### **Security Hardening**

#### **API Security**
```python
# Rate limiting configuration
RATE_LIMITS = {
    "quiz_generation": "10/minute",
    "pdf_upload": "5/minute", 
    "debug_endpoints": "20/minute"
}

# CORS configuration
ALLOWED_ORIGINS = [
    "https://yourdomain.com",
    "https://app.yourdomain.com"
]

# Request validation
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_FILE_TYPES = [".pdf"]
```

#### **Infrastructure Security**
- **Network Isolation**: Private subnets for databases
- **TLS Encryption**: HTTPS for all external communication
- **API Key Rotation**: Regular credential updates
- **Firewall Rules**: Restrict access to necessary ports only
- **Container Security**: Non-root user, minimal base images

## 🚨 Troubleshooting

### **Common Issues & Solutions**

#### **Worker Not Processing Tasks**
**Symptoms:** PDF uploads stuck in "pending" status, no background processing

**Diagnosis:**
```bash
# Check worker status
curl http://localhost:8000/readyz

# Check Celery worker logs
docker-compose logs celery_worker

# Verify Redis connectivity
redis-cli -h localhost -p 6379 ping
```

**Solutions:**
```bash
# Restart worker
start-worker.bat  # Windows
python -m celery -A app.worker worker --loglevel=info  # Manual

# Check Redis connection
redis-cli monitor  # Monitor Redis commands

# Verify task queue
redis-cli -h localhost -p 6379 llen celery
```

#### **PDF Upload Failures**
**Common Causes:**
- File size exceeds 50MB limit
- Corrupted or password-protected PDF
- Insufficient disk space
- Permission issues in uploads directory

**Diagnosis:**
```bash
# Check file size
ls -lh uploads/

# Verify disk space
df -h

# Check directory permissions
ls -la uploads/

# Review upload logs
grep "ingest" logs/app.log
```

**Solutions:**
```bash
# Increase file size limit (if needed)
# Edit app/core/settings.py: max_file_size = 100 * 1024 * 1024

# Fix permissions
chmod 755 uploads/
chown -R app:app uploads/

# Clean old uploads
find uploads/ -name "*.pdf" -mtime +7 -delete
```

#### **Quiz Generation Errors**
**Symptoms:** HTTP 500 errors, timeout failures, malformed responses

**Diagnosis:**
```bash
# Check API key configuration
env | grep -E "(COHERE|GROQ)_API_KEY"

# Test network connectivity
curl -I https://api.groq.com
curl -I https://api.cohere.ai

# Review generation logs
grep "quiz.generation" logs/app.log | tail -20
```

**Solutions:**
```bash
# Verify API keys are valid
curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/v1/models

# Check rate limiting
grep "rate.limit" logs/app.log

# Test with smaller requests
# Reduce num_questions or try different topics
```

#### **Search Performance Issues**
**Symptoms:** Slow quiz generation, empty search results, poor question quality

**Diagnosis:**
```bash
# Check Weaviate health
curl http://localhost:8080/v1/meta

# Test search endpoint
curl "http://localhost:8000/api/v1/quizzes/debug/search/test?session_id=your-session"

# Monitor embedding performance
grep "embedding" logs/app.log
```

**Solutions:**
```bash
# Restart Weaviate
docker-compose restart weaviate

# Check index size and memory
curl http://localhost:8080/v1/schema

# Optimize chunk size in app/utils/splitters.py
# Reduce chunk_size if memory issues
# Increase overlap if context issues
```

#### **Memory and Performance Issues**
**Symptoms:** Slow responses, high memory usage, container restarts

**Monitoring:**
```bash
# Check memory usage
docker stats

# Monitor API response times
curl -w "Total time: %{time_total}s\n" http://localhost:8000/livez

# Review resource usage logs
grep -E "(memory|cpu|performance)" logs/app.log
```

**Optimization:**
```bash
# Reduce worker concurrency
# Edit docker-compose.yml: --concurrency=2

# Optimize embeddings batch size
# Edit app/core/settings.py: embedding_batch_size = 50

# Clean up old sessions
curl -X DELETE http://localhost:8000/api/v1/sessions/old-session-id
```

#### **Network and Connectivity Issues**
**Symptoms:** External API failures, timeout errors, DNS resolution issues

**Diagnosis:**
```bash
# Test DNS resolution
nslookup api.groq.com
nslookup api.cohere.ai

# Check network connectivity
ping 8.8.8.8

# Test API endpoints
curl -v https://api.groq.com/v1/models
```

**Solutions:**
```bash
# Configure DNS servers
echo "nameserver 8.8.8.8" >> /etc/resolv.conf

# Check firewall rules
iptables -L

# Use proxy if needed
export https_proxy=http://proxy:8080
```

### **Debug Mode & Logging**

#### **Enable Debug Logging**
```bash
# Set environment variable
export LOG_LEVEL=DEBUG

# Or in .env file
LOG_LEVEL=DEBUG
STRUCTLOG_LEVEL=DEBUG
```

#### **Useful Debug Endpoints**
```bash
# Test search functionality
curl "http://localhost:8000/api/v1/quizzes/debug/search-detailed/machine%20learning"

# Check indexed content
curl "http://localhost:8000/api/v1/quizzes/debug/indexed-content-detailed"

# Session information
curl "http://localhost:8000/api/v1/sessions/your-session-id/info"
```

#### **Log Analysis**
```bash
# Filter by component
grep "search\." logs/app.log
grep "quiz\.generation" logs/app.log
grep "pdf\.ingestion" logs/app.log

# Monitor real-time logs
tail -f logs/app.log | grep ERROR

# Check specific session
grep "session_id=your-session-id" logs/app.log
```

### **Performance Monitoring**

#### **Key Metrics to Watch**
```bash
# API response times
curl -w "@curl-format.txt" http://localhost:8000/api/v1/quizzes/generate

# Memory usage
free -h
docker stats --no-stream

# Disk usage
du -sh uploads/
du -sh logs/
```

#### **Health Check Script**
```bash
#!/bin/bash
# health_check.sh

echo "=== System Health Check ==="

# API Health
if curl -f http://localhost:8000/livez > /dev/null 2>&1; then
    echo "✅ API is responding"
else
    echo "❌ API is down"
fi

# Worker Health
if curl -s http://localhost:8000/readyz | grep -q "healthy"; then
    echo "✅ Celery worker is healthy"
else
    echo "❌ Celery worker issues"
fi

# Database Health
if curl -f http://localhost:8080/v1/meta > /dev/null 2>&1; then
    echo "✅ Weaviate is responding"
else
    echo "❌ Weaviate is down"
fi

# Redis Health
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is responding"
else
    echo "❌ Redis is down"
fi

echo "=== End Health Check ==="
```

### **Support Resources**

#### **Log Locations**
- **Application Logs**: `logs/app.log`
- **Celery Logs**: `logs/celery.log`
- **Docker Logs**: `docker-compose logs [service]`
- **System Logs**: `/var/log/syslog` (Linux)

#### **Configuration Files**
- **Main Config**: `app/core/settings.py`
- **Environment**: `.env`
- **Docker Config**: `docker-compose.yml`
- **Worker Config**: `app/worker.py`

#### **Useful Commands**
```bash
# Complete system restart
docker-compose down && docker-compose up -d

# Reset all data
docker-compose down -v
rm -rf uploads/* exports/*

# View all services status
docker-compose ps

# Follow all logs
docker-compose logs -f
```

## 🔒 Security Considerations

- **Input Validation**: Comprehensive request sanitization
- **File Upload Security**: Type validation, size limits, malware scanning
- **API Key Management**: Secure environment variable handling
- **Rate Limiting**: Prevent abuse and resource exhaustion
- **Session Isolation**: Strict content access controls
- **Error Information**: Sanitized error messages to prevent information leakage

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
- Check the troubleshooting section above
- Review API documentation at `/api/v1/docs`
- Examine application logs for detailed error information
- Monitor health endpoints for service status

---

**Built with ❤️ using modern AI and retrieval technologies**
