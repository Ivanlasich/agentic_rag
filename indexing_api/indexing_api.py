#!/usr/bin/env python3
"""
FastAPI приложение для индексации документов в Qdrant по доменам
"""

import os
import uuid
from typing import List, Optional
from pathlib import Path
import re
import tqdm
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiofiles
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams, PointStruct
import requests
import httpx
import json
from file_parser import file_parser
from auth_api import auth_router
from auth_jwt import get_current_user, require_admin, require_user_or_admin
from auth_models import User

# Конфигурация
QDRANT_URL = "http://localhost:6335"
EMBEDDING_MODEL_URL = "http://172.17.0.1:8089"
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
DOMAINS_SUMMARY_DIR = "domains_summary"
CHUNK_SIZE = 1000  # Размер чанка для обработки текста

# Создаем директории
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOMAINS_SUMMARY_DIR, exist_ok=True)

app = FastAPI(
    title="Document Indexing API",
    description="API для индексации документов в Qdrant по доменам",
    version="1.0.0"
)

# Добавляем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # React dev server
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Подключаем роутер аутентификации
app.include_router(auth_router)

# Инициализация Qdrant клиента
# Prefer Docker service URL from env; fallback to in-network service name
import os as _os
_qdrant_url = _os.getenv("QDRANT_URL", "http://qdrant-domains:6333")
qdrant_client = QdrantClient(url=_qdrant_url)

class IndexingResponse(BaseModel):
    domain: str
    collection_name: str
    files_processed: List[str]
    documents_indexed: int
    status: str

class CollectionInfo(BaseModel):
    name: str
    documents_count: int
    status: str

class DomainSummaryResponse(BaseModel):
    domain_name: str
    files_analyzed: List[str]
    summary: str
    status: str

def extract_table_of_contents(text: str) -> str:
    """Извлекает содержание из начала файла"""
    lines = text.split('\n')
    toc_lines = []
    in_toc = False
    
    for line in lines[:500]:  # Проверяем первые 50 строк
        line = line.strip()
        if not line:
            continue
            
        # Ищем начало содержания
        if any(keyword in line.lower() for keyword in ['содержание', 'оглавление', 'table of contents', 'contents']):
            in_toc = True
            continue
            
        # Если мы в содержании и встречаем обычный текст (не содержание)
        if in_toc:
            # Проверяем, что это не начало основного текста
            if len(line) > 100 and not any(char.isdigit() for char in line[:10]):
                break
            # Добавляем строки содержания
            if line and (line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')) or 
                        re.match(r'^\d+\.', line) or 
                        line.startswith(('Глава', 'Раздел', 'Часть', 'Chapter', 'Section'))):
                toc_lines.append(line)
    
    return '\n'.join(toc_lines) if toc_lines else text[:500]  # Если содержание не найдено, берем первые 500 символов

async def get_embedding(text: str) -> List[float]:
    """Получение эмбеддинга для текста через TEI модель"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{EMBEDDING_MODEL_URL}/embed",
                json={"inputs": text},
                timeout=30
            )
            response.raise_for_status()
            return response.json()[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения эмбеддинга: {str(e)}")

def create_collection_if_not_exists(collection_name: str):
    """Создание коллекции если она не существует"""
    try:
        # Проверяем существование коллекции
        collections = qdrant_client.get_collections()
        existing_collections = [col.name for col in collections.collections]
        
        if collection_name not in existing_collections:
            # Создаем коллекцию с именованным вектором для совместимости с MCP сервером
            vector_name = f"tei-{EMBEDDING_MODEL_URL.split('//')[1].replace(':', '-')}"
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    vector_name: VectorParams(size=1024, distance=Distance.COSINE)
                }
            )
            print(f"Создана коллекция: {collection_name} с вектором: {vector_name}")
        else:
            print(f"Коллекция {collection_name} уже существует")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания коллекции: {str(e)}")

def process_text_file(file_path: str) -> List[str]:
    """Обработка текстового файла и разбиение на чанки"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Простое разбиение на чанки по символам
        chunks = []
        for i in range(0, len(content), CHUNK_SIZE):
            chunk = content[i:i + CHUNK_SIZE].strip()
            if chunk:
                chunks.append(chunk)
        
        return chunks
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки файла {file_path}: {str(e)}")

async def index_documents_to_collection(collection_name: str, documents: List[str], file_names: List[str]):
    """Индексация документов в коллекцию"""
    try:
        points = []
        vector_name = f"tei-{EMBEDDING_MODEL_URL.split('//')[1].replace(':', '-')}"
        
        for i, doc in tqdm.tqdm(enumerate(documents)):
            # Получаем эмбеддинг
            embedding = await get_embedding(doc)
            
            # Создаем точку для Qdrant с именованным вектором
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector={vector_name: embedding},
                payload={
                    "document": doc,
                    "domain": collection_name,
                    "source_files": file_names,
                    "chunk_index": i,
                    "total_chunks": len(documents)
                }
            )
            points.append(point)
        
        # Добавляем точки в коллекцию
        qdrant_client.upsert(
            collection_name=collection_name,
            points=points
        )
        
        return len(points)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка индексации: {str(e)}")

@app.get("/")
async def root():
    """Корневой endpoint"""
    return {"message": "Document Indexing API", "version": "1.0.0"}

@app.get("/collections", response_model=List[CollectionInfo])
async def get_collections(current_user: User = Depends(require_user_or_admin)):
    """Получение списка всех коллекций"""
    #try:
    if True:
        collections = qdrant_client.get_collections()
        result = []
        
        for collection in collections.collections:
            # Получаем информацию о коллекции
            info = qdrant_client.get_collection(collection.name)
            result.append(CollectionInfo(
                name=collection.name,
                documents_count=info.points_count,
                status=info.status.value
            ))
        
        return result
    #except Exception as e:
    #    raise HTTPException(status_code=500, detail=f"Ошибка получения коллекций: {str(e)}")

@app.post("/index", response_model=IndexingResponse)
async def index_documents(
    domain: str = Form(..., description="Название домена (будет использовано как имя коллекции)"),
    files: List[UploadFile] = File(..., description="Файлы для индексации"),
    current_user: User = Depends(require_user_or_admin)
):
    """
    Индексация документов в указанный домен
    
    Args:
        domain: Название домена (будет использовано как имя коллекции)
        files: Список файлов для индексации
    """
    if not files:
        raise HTTPException(status_code=400, detail="Не указаны файлы для индексации")
    
    if not domain:
        raise HTTPException(status_code=400, detail="Не указан домен")
    
    # Очищаем домен от недопустимых символов
    collection_name = domain.lower().replace(" ", "_").replace("-", "_")
    
    #try:
    if True:
        # Создаем коллекцию если не существует
        create_collection_if_not_exists(collection_name)
        
        # Создаем папку для домена если не существует
        domain_folder = os.path.join(UPLOAD_DIR, collection_name)
        os.makedirs(domain_folder, exist_ok=True)
        
        # Обрабатываем файлы
        all_documents = []
        processed_files = []
        
        for file in files:
            if not file.filename:
                continue
                
            # Сохраняем оригинальный файл в папку домена
            original_file_path = os.path.join(domain_folder, file.filename)
            async with aiofiles.open(original_file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            # Создаем путь для текстового файла
            file_name_without_ext = os.path.splitext(file.filename)[0]
            txt_file_path = os.path.join(domain_folder, f"{file_name_without_ext}.txt")
            
            # Конвертируем файл в текст и сохраняем
            conversion_success = await file_parser.convert_and_save_as_txt(
                original_file_path, txt_file_path
            )
            
            if conversion_success:
                # Обрабатываем текстовый файл
                documents = process_text_file(txt_file_path)
                all_documents.extend(documents)
                processed_files.append(file.filename)
            else:
                # Если конвертация не удалась, пробуем обработать как текстовый файл
                documents = process_text_file(original_file_path)
                if documents:
                    all_documents.extend(documents)
                    processed_files.append(file.filename)
                else:
                    print(f"Не удалось обработать файл: {file.filename}")
            
            # НЕ удаляем файлы - оставляем в папке домена для архива
        
        if not all_documents:
            raise HTTPException(status_code=400, detail="Не удалось извлечь текст из файлов")
        
        # Индексируем документы
        indexed_count = await index_documents_to_collection(
            collection_name, 
            all_documents, 
            processed_files
        )
        
        # Создаем суммаризацию домена
        try:
            await create_domain_summary_internal(collection_name)
        except Exception as e:
            print(f"Ошибка создания суммаризации: {e}")
        
        return IndexingResponse(
            domain=domain,
            collection_name=collection_name,
            files_processed=processed_files,
            documents_indexed=indexed_count,
            status="success"
        )
    '''
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")
    '''
'''
@app.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """Удаление коллекции"""
    try:
        qdrant_client.delete_collection(collection_name)
        return {"message": f"Коллекция {collection_name} удалена"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления коллекции: {str(e)}")
'''
@app.get("/collections/{collection_name}/info")
async def get_collection_info(collection_name: str, current_user: User = Depends(require_user_or_admin)):
    """Получение информации о коллекции"""
    try:
        info = qdrant_client.get_collection(collection_name)
        return {
            "name": collection_name,
            "points_count": info.points_count,
            "status": info.status.value,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения информации о коллекции: {str(e)}")

@app.post("/collections")
async def create_collection(request: dict, current_user: User = Depends(require_admin)):
    """
    Создание новой коллекции
    """
    try:
        collection_name = request.get('collection_name')
        vectors_config = request.get('vectors_config', {})
        
        if not collection_name:
            raise HTTPException(status_code=400, detail="Не указано название коллекции")
        
        # Проверяем, существует ли коллекция
        if qdrant_client.collection_exists(collection_name=collection_name):
            raise HTTPException(status_code=400, detail=f"Коллекция '{collection_name}' уже существует")
        
        # Создаем коллекцию с именованным вектором для совместимости с MCP сервером
        vector_name = f"tei-{EMBEDDING_MODEL_URL.split('//')[1].replace(':', '-')}"
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={
                vector_name: models.VectorParams(
                    size=vectors_config.get('size', 1024),
                    distance=models.Distance.COSINE
                )
            }
        )
        
        # Создаем папку для домена в uploads
        domain_folder = os.path.join(UPLOAD_DIR, collection_name)
        os.makedirs(domain_folder, exist_ok=True)
        
        return {
            "message": f"Коллекция '{collection_name}' успешно создана с вектором '{vector_name}'",
            "collection_name": collection_name,
            "vector_name": vector_name,
            "domain_folder": domain_folder
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания коллекции: {str(e)}")

@app.get("/collections/{collection_name}/files")
async def get_domain_files(collection_name: str, current_user: User = Depends(require_user_or_admin)):
    """
    Получение списка файлов в домене
    """
    try:
        domain_folder = os.path.join(UPLOAD_DIR, collection_name)
        
        if not os.path.exists(domain_folder):
            return {"files": []}
        
        files = []
        for filename in os.listdir(domain_folder):
            file_path = os.path.join(domain_folder, filename)
            if os.path.isfile(file_path):
                stat = os.stat(file_path)
                files.append({
                    "name": filename,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "path": file_path
                })
        
        # Сортируем по дате изменения (новые сверху)
        files.sort(key=lambda x: x["modified"], reverse=True)
        
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения файлов домена: {str(e)}")

@app.delete("/collections/{collection_name}/files/{filename}")
async def delete_domain_file(collection_name: str, filename: str, current_user: User = Depends(require_admin)):
    """
    Удаление файла из домена и реиндексация коллекции
    """
    try:
        domain_folder = os.path.join(UPLOAD_DIR, collection_name)
        file_path = os.path.join(domain_folder, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Файл '{filename}' не найден в домене '{collection_name}'")
        
        # Удаляем файл
        os.remove(file_path)
        
        # Получаем все оставшиеся файлы в домене
        remaining_files = []
        if os.path.exists(domain_folder):
            for f in os.listdir(domain_folder):
                file_path = os.path.join(domain_folder, f)
                if os.path.isfile(file_path):
                    remaining_files.append(file_path)
        '''
        # Очищаем коллекцию
        qdrant_client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source_files",
                            match=models.MatchValue(value=filename)
                        )
                    ]
                )
            )
        )
        
        # Если есть оставшиеся файлы, реиндексируем их
        if remaining_files:
            all_documents = []
            for file_path in remaining_files:
                documents = process_text_file(file_path)
                all_documents.extend(documents)
            
            if all_documents:
                indexed_count = index_documents_to_collection(
                    collection_name, all_documents
                )
                return {
                    "message": f"Файл '{filename}' удален и коллекция реиндексирована",
                    "deleted_file": filename,
                    "remaining_files": len(remaining_files),
                    "reindexed_documents": indexed_count
                }
        '''
        return {
            "message": f"Файл '{filename}' удален, коллекция '{collection_name}' не очищена",
            "deleted_file": filename,
            "remaining_files": 0,
            "reindexed_documents": 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления файла: {str(e)}")

@app.post("/collections/{collection_name}/reindex")
async def reindex_domain(collection_name: str, current_user: User = Depends(require_admin)):
    """
    Полная реиндексация домена (очистка и переиндексация всех файлов)
    """
    try:
        domain_folder = os.path.join(UPLOAD_DIR, collection_name)
        
        if not os.path.exists(domain_folder):
            raise HTTPException(status_code=404, detail=f"Домен '{collection_name}' не найден")
        
        # Получаем все файлы в домене
        files = []
        for filename in os.listdir(domain_folder):
            file_path = os.path.join(domain_folder, filename)
            if os.path.isfile(file_path):
                files.append(file_path)
        
        if not files:
            raise HTTPException(status_code=400, detail=f"В домене '{collection_name}' нет файлов для индексации")
        
        # Очищаем коллекцию
        qdrant_client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="domain",
                            match=models.MatchValue(value=collection_name)
                        )
                    ]
                )
            )
        )
        
        # Обрабатываем все файлы
        all_documents = []
        processed_files = []
        
        for file_path in files:
            file_name = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # Если это уже текстовый файл, обрабатываем напрямую
            if file_ext in ['.txt', '.md', '.rst']:
                documents = process_text_file(file_path)
                if documents:
                    all_documents.extend(documents)
                    processed_files.append(file_name)
            '''
            else:
                # Для других форматов конвертируем в текст
                file_name_without_ext = os.path.splitext(file_name)[0]
                txt_file_path = os.path.join(domain_folder, f"{file_name_without_ext}.txt")
                
                # Конвертируем файл в текст
                conversion_success = await file_parser.convert_and_save_as_txt(
                    file_path, txt_file_path
                )
                
                if conversion_success:
                    documents = process_text_file(txt_file_path)
                    if documents:
                        all_documents.extend(documents)
                        processed_files.append(file_name)
                else:
                    print(f"Не удалось конвертировать файл: {file_name}")
            '''
        if not all_documents:
            raise HTTPException(status_code=400, detail="Не удалось извлечь текст из файлов")
        
        # Индексируем документы
        indexed_count = await index_documents_to_collection(
            collection_name, all_documents, processed_files
        )
        
        # Создаем суммаризацию домена
        try:
            await create_domain_summary_internal(collection_name)
        except Exception as e:
            print(f"Ошибка создания суммаризации: {e}")
        
        return {
            "message": f"Домен '{collection_name}' успешно реиндексирован",
            "processed_files": processed_files,
            "indexed_documents": indexed_count,
            "total_files": len(files)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка реиндексации: {str(e)}")

async def create_domain_summary_internal(collection_name: str):
    """Внутренняя функция для создания суммаризации домена"""
    try:
        domain_path = os.path.join(UPLOAD_DIR, collection_name)
        
        if not os.path.exists(domain_path):
            print(f"Домен '{collection_name}' не найден для суммаризации")
            return
        
        # Получаем список файлов в домене
        files = []
        for file_name in os.listdir(domain_path):
            file_path = os.path.join(domain_path, file_name)
            if os.path.isfile(file_path) and file_name.endswith(('.txt', '.md', '.rst')):
                files.append(file_path)
        
        if not files:
            print(f"В домене '{collection_name}' нет текстовых файлов для суммаризации")
            return
        
        # Извлекаем содержания из файлов
        contents_list = []
        
        for file_path in files:
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    
                # Извлекаем содержание
                toc = extract_table_of_contents(content)
                contents_list.append(toc)
                
            except Exception as e:
                print(f"Ошибка при обработке файла {file_path}: {e}")
                continue
        
        if not contents_list:
            print("Не удалось извлечь содержание из файлов для суммаризации")
            return
        
        # Создаем суммаризацию через LLM
        summary = create_domain_summary_with_llm(collection_name, contents_list)
        
        # Сохраняем суммаризацию в файл
        summary_file_path = os.path.join(DOMAINS_SUMMARY_DIR, f"{collection_name}_summary.txt")
        async with aiofiles.open(summary_file_path, 'w', encoding='utf-8') as f:
            await f.write(summary)
        
        print(f"✅ Суммаризация домена '{collection_name}' создана успешно")
        
    except Exception as e:
        print(f"Ошибка создания внутренней суммаризации: {e}")

def create_domain_summary_with_llm(domain_name: str, contents_list: List[str]) -> str:
    """Создает суммаризацию домена через Qwen LLM"""
    try:
        # Объединяем все содержания
        combined_contents = "\n\n".join(contents_list)
        
        # Создаем промпт для суммаризации
        prompt = f"""Проанализируй следующие содержания документов из домена "{domain_name}" и создай краткое описание домена:

{combined_contents}

Создай краткое описание домена (2-3 предложения), которое поможет понять:
1. О чем этот домен
2. Какие основные темы/разделы он покрывает
3. Для чего он может быть полезен

Ответ должен быть на русском языке и не более 200 слов."""

        # Отправляем запрос к Qwen LLM (vLLM OpenAI-compatible API)
        qwen_url = "http://localhost:19000/v1/chat/completions"
        
        response = requests.post(
            qwen_url,
            json={
                "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.3,
                "stream": False
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                # Убираем лишние пробелы и переносы строк
                content = content.strip()
                return content if content else "Не удалось создать суммаризацию"
            else:
                return "Не удалось создать суммаризацию"
        else:
            print(f"Ошибка запроса к Qwen: {response.status_code} - {response.text}")
            # Создаем простую суммаризацию
            return f"Домен '{domain_name}' содержит {len(contents_list)} документов с различными темами и разделами."
            
    except Exception as e:
        print(f"Ошибка при создании суммаризации через Qwen: {e}")
        return f"Домен '{domain_name}' содержит {len(contents_list)} документов."

@app.post("/collections/{collection_name}/summarize", response_model=DomainSummaryResponse)
async def summarize_domain(collection_name: str, current_user: User = Depends(require_user_or_admin)):
    """
    Анализ домена и создание краткого описания
    """
    try:
        domain_path = os.path.join(UPLOAD_DIR, collection_name)
        
        if not os.path.exists(domain_path):
            raise HTTPException(status_code=404, detail=f"Домен '{collection_name}' не найден")
        
        # Получаем список файлов в домене
        files = []
        for file_name in os.listdir(domain_path):
            file_path = os.path.join(domain_path, file_name)
            if os.path.isfile(file_path) and file_name.endswith(('.txt', '.md', '.rst')):
                files.append(file_path)
        
        if not files:
            raise HTTPException(status_code=400, detail=f"В домене '{collection_name}' нет текстовых файлов")
        
        # Извлекаем содержания из файлов
        contents_list = []
        processed_files = []
        
        for file_path in files:
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    
                # Извлекаем содержание
                toc = extract_table_of_contents(content)
                contents_list.append(toc)
                processed_files.append(os.path.basename(file_path))
                
            except Exception as e:
                print(f"Ошибка при обработке файла {file_path}: {e}")
                continue
        
        if not contents_list:
            raise HTTPException(status_code=400, detail="Не удалось извлечь содержание из файлов")
        
        # Создаем суммаризацию через LLM
        summary = create_domain_summary_with_llm(collection_name, contents_list)
        
        # Сохраняем суммаризацию в файл
        summary_file_path = os.path.join(DOMAINS_SUMMARY_DIR, f"{collection_name}_summary.txt")
        async with aiofiles.open(summary_file_path, 'w', encoding='utf-8') as f:
            await f.write(summary)
        
        return DomainSummaryResponse(
            domain_name=collection_name,
            files_analyzed=processed_files,
            summary=summary,
            status="success"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания суммаризации: {str(e)}")

@app.get("/collections/{collection_name}/summary")
async def get_domain_summary(collection_name: str, current_user: User = Depends(require_user_or_admin)):
    """
    Получение суммаризации домена
    """
    try:
        summary_file_path = os.path.join(DOMAINS_SUMMARY_DIR, f"{collection_name}_summary.txt")
        
        if not os.path.exists(summary_file_path):
            raise HTTPException(status_code=404, detail=f"Суммаризация для домена '{collection_name}' не найдена")
        
        async with aiofiles.open(summary_file_path, 'r', encoding='utf-8') as f:
            summary = await f.read()
        
        return {
            "domain_name": collection_name,
            "summary": summary,
            "timestamp": os.path.getmtime(summary_file_path)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения суммаризации: {str(e)}")

@app.get("/domains/summaries")
async def list_domain_summaries(current_user: User = Depends(require_user_or_admin)):
    """
    Получение списка всех суммаризаций доменов
    """
    try:
        summaries = []
        
        for file_name in os.listdir(DOMAINS_SUMMARY_DIR):
            if file_name.endswith('_summary.txt'):
                domain_name = file_name.replace('_summary.txt', '')
                summary_file_path = os.path.join(DOMAINS_SUMMARY_DIR, file_name)
                
                async with aiofiles.open(summary_file_path, 'r', encoding='utf-8') as f:
                    summary = await f.read()
                
                summaries.append({
                    "domain_name": domain_name,
                    "summary": summary,
                    "timestamp": os.path.getmtime(summary_file_path)
                })
        
        return {
            "summaries": summaries,
            "count": len(summaries)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения списка суммаризаций: {str(e)}")

@app.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str, current_user: User = Depends(require_admin)):
    """
    Удаление коллекции
    """
    try:
        if not qdrant_client.collection_exists(collection_name=collection_name):
            raise HTTPException(status_code=404, detail=f"Коллекция '{collection_name}' не найдена")
        
        qdrant_client.delete_collection(collection_name=collection_name)
        
        # Удаляем папку домена
        domain_folder = os.path.join(UPLOAD_DIR, collection_name)
        if os.path.exists(domain_folder):
            import shutil
            shutil.rmtree(domain_folder)
        
        return {"message": f"Коллекция '{collection_name}' и её файлы успешно удалены"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления коллекции: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)

