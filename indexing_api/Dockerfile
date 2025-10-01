FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Install Python deps with pinned versions
RUN pip install --no-cache-dir \
    fastapi==0.118.0 \
    uvicorn[standard]==0.37.0 \
    python-dotenv==1.1.1 \
    aiofiles==24.1.0 \
    qdrant-client==1.15.1 \
    requests==2.32.5 \
    httpx==0.28.1 \
    tqdm==4.67.1 \
    sqlalchemy==2.0.43 \
    passlib[bcrypt]==1.7.4 \
    bcrypt==4.1.2 \
    python-jose[cryptography]==3.5.0 \
    python-multipart==0.0.20 \
    PyJWT==2.10.1 \
    email-validator==2.3.0 \
    PyPDF2==3.0.1


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

