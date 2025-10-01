FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Install Python deps
# Pin bcrypt to avoid passlib compatibility warnings and backend issues
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-dotenv \
    aiofiles \
    qdrant-client \
    requests \
    httpx \
    tqdm \
    sqlalchemy \
    passlib[bcrypt]==1.7.4 \
    bcrypt==4.1.2 \
    python-jose[cryptography] \
    python-multipart \
    PyJWT \
    email-validator \
    PyPDF2


# Copy source
COPY . /app/indexing_api
WORKDIR /app/indexing_api

# Environment defaults (override in compose)
ENV QDRANT_URL=http://qdrant-domains:6333
ENV EMBEDDING_MODEL_URL=http://172.17.0.1:8089
ENV UPLOAD_DIR=uploads
ENV DOMAINS_SUMMARY_DIR=domains_summary
ENV CHUNK_SIZE=1000

# Create dirs on startup
RUN mkdir -p /app/uploads /app/domains_summary

EXPOSE 8009

CMD ["python", "indexing_api.py"]

