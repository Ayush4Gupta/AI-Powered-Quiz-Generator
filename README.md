# AI-Powered Quiz Generator

An intelligent quiz generation system that creates multiple-choice questions from PDF documents using advanced AI and retrieval techniques.

## 🚀 Features

- **Multi-Strategy Search**: Combines Hybrid Search, HyDE (Hypothetical Document Embeddings), and BM25 fallback
- **RAG Pipeline**: Retrieval-Augmented Generation with PDF document ingestion
- **Session Management**: Isolated content processing per user session
- **Background Processing**: Async PDF processing with Celery
- **Offline Fallback**: Continues working without internet connectivity
- **Production Ready**: Docker containerization, monitoring, and comprehensive API

## 🛠️ Tech Stack

- **Backend**: FastAPI, Python 3.11+
- **AI/ML**: Deepseek R1, Cohere, Sentence Transformers
- **Vector DB**: Weaviate
- **Queue**: Celery + Redis
- **Monitoring**: Prometheus, Structured Logging
- **Deployment**: Docker, Docker Compose

## 🏃 Quick Start

```bash
# Clone repository
git clone https://github.com/Ayush4Gupta/AI-Powered-Quiz-Generator.git
cd AI-Powered-Quiz-Generator

# Setup environment
cp .env.example .env
# Edit .env with your API keys

# Run with Docker
docker-compose up -d

# Or run locally
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 🔧 Configuration

Set these environment variables in `.env`:
```bash
COHERE_API_KEY=your_cohere_key
GROQ_API_KEY=your_groq_key
WEAVIATE_URL=http://localhost:8080
CELERY_BROKER_URL=redis://localhost:6379/0
```

## 📚 API Endpoints

- `POST /api/v1/quizzes/generate` - Generate quiz from topic
- `POST /api/v1/quizzes/ingest` - Upload PDF documents
- `GET /api/v1/sessions/list` - Manage content sessions
- `GET /docs` - Interactive API documentation

## 🧠 How It Works

1. **Upload PDF** → Text extraction and chunking
2. **Embedding Generation** → Store in Weaviate vector database
3. **Query Processing** → Multi-strategy search (Hybrid + HyDE + BM25)
4. **Quiz Generation** → AI-powered question creation with multiple variants

## 📈 Advanced Features

- **HyDE Search**: Generates synthetic documents to bridge vocabulary gaps
- **Multi-Variant Quizzes**: Creates diverse question sets from same content
- **Smart Reranking**: Neural reranking with Cohere for optimal results
- **Session Isolation**: Prevents data leakage between different document sets

## 🤝 Contributing

Contributions welcome! Please read the contributing guidelines and submit pull requests.

## 📄 License

MIT License - see LICENSE file for details.
```

This README is concise but covers all the essential information someone needs to understand and use your project. You can copy this to GitHub and edit it as needed!This README is concise but covers all the essential information someone needs to understand and use your project. You can copy this to GitHub and edit it as needed!
