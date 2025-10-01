import aiohttp
import asyncio
from typing import List, Union

from mcp_server_qdrant.embeddings.base import EmbeddingProvider


class TEIProvider(EmbeddingProvider):
    """
    TEI (Text Embeddings Inference) implementation of the embedding provider.
    Connects to external TEI services via HTTP API.
    
    :param tei_url: The URL of the TEI service (e.g., http://localhost:8089)
    :param timeout: Request timeout in seconds
    :param max_retries: Maximum number of retry attempts
    """
    
    def __init__(self, tei_url: str, timeout: int = 30, max_retries: int = 3):
        self.tei_url = tei_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session
    
    async def _make_request(self, payload: dict) -> List[List[float]]:
        """Make HTTP request to TEI service with retry logic."""
        session = await self._get_session()
        
        for attempt in range(self.max_retries):
            try:
                async with session.post(
                    f"{self.tei_url}/embed",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # TEI возвращает List[List[float]] напрямую
                        if isinstance(result, list):
                            # Проверяем, что все элементы - списки чисел
                            if all(isinstance(item, list) and all(isinstance(x, (int, float)) for x in item) for item in result):
                                return result
                            else:
                                raise Exception(f"Unexpected response format: {type(result)}")
                        else:
                            raise Exception(f"Expected list response, got {type(result)}")
                    else:
                        error_text = await response.text()
                        raise Exception(f"TEI service error {response.status}: {error_text}")
                        
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise Exception(f"Failed to get embeddings after {self.max_retries} attempts: {e}")
                
                # Wait before retry (exponential backoff)
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        raise Exception("Unexpected error in retry loop")
    
    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Embed a list of documents into vectors."""
        if not documents:
            return []
            
        payload = {"inputs": documents, "model": "BAAI/bge-m3"}
        embeddings = await self._make_request(payload)
        
        # Ensure we return the right number of embeddings
        if len(embeddings) != len(documents):
            raise Exception(f"Expected {len(documents)} embeddings, got {len(embeddings)}")
            
        return embeddings
    
    async def embed_query(self, query: str) -> List[float]:
        """Embed a query into a vector."""
        payload = {"inputs": [query], "model": "BAAI/bge-m3"}
        embeddings = await self._make_request(payload)
        
        if not embeddings or len(embeddings) == 0:
            raise Exception("No embeddings returned for query")
            
        return embeddings[0]
    
    def get_vector_name(self) -> str:
        """Return the name of the vector for the Qdrant collection."""
        # Extract hostname from URL for vector naming
        from urllib.parse import urlparse
        parsed = urlparse(self.tei_url)
        hostname = parsed.hostname or "tei"
        port = parsed.port or ""
        port_suffix = f"-{port}" if port else ""
        return f"tei-{hostname}{port_suffix}"
    
    def get_vector_size(self) -> int:
        """Get the size of the vector for the Qdrant collection."""
        return 1024  # Ваш TEI сервис возвращает векторы размерности 1024
        
    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        if self._session and not self._session.closed:
            # Schedule cleanup in event loop if available
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
            except RuntimeError:
                pass
