FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Install Python deps
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-dotenv \
    langchain-openai \
    httpx \
    pydantic \
    PyYAML \
    mcp-use

# Optional MCP client lib if available
RUN pip install --no-cache-dir mcp-use || true

# Copy source
COPY . /app/agentic_rag
WORKDIR /app/agentic_rag

# Environment defaults (override in compose)
ENV UPLOADS_PATH=/app/uploads
ENV SUMMARY_PATH=/app/domains_summary
ENV OPENAI_BASE_URL=http://172.17.0.1:19000/v1
ENV OPENAI_API_KEY=dummy-key

# Create dirs on startup
RUN mkdir -p /app/uploads /app/domains_summary

EXPOSE 8663

CMD ["python", "qdrant_msp_use_agent.py"]