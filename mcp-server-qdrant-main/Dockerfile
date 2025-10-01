FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for aiohttp
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy source code
COPY . .

# Install dependencies and package in system Python
RUN pip install aiohttp>=3.8.0
RUN pip install -e .

# Set PYTHONPATH to use local code
ENV PYTHONPATH="/app/src:${PYTHONPATH}"

# Expose the default port for SSE transport
EXPOSE 8000

# Set environment variables with defaults that can be overridden at runtime
ENV QDRANT_URL=""
ENV QDRANT_API_KEY=""
ENV COLLECTION_NAME="default-collection"
ENV EMBEDDING_PROVIDER="fastembed"
ENV EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"

# Run the server using the installed script
CMD ["mcp-server-qdrant", "--transport", "sse"]
