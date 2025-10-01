# Agentic RAG System

Система агентного поиска и генерации ответов (RAG) с поддержкой векторных баз данных и индексации документов.

## Архитектура

Система состоит из 4 основных сервисов:

- **Qdrant Domains** - векторная база данных для хранения эмбеддингов
- **MCP Server Qdrant** - сервер для взаимодействия с Qdrant через MCP протокол
- **Indexing API** - API для индексации и загрузки документов
- **Agentic RAG** - основной сервис для агентного поиска и генерации ответов

## Требования

- Docker и Docker Compose
- Python 3.11+ (для локальной разработки)
- Embedding модель (например, Text Embedding Inference)

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone https://github.com/Ivanlasich/agentic_rag.git
cd agentic_rag
```

### 2. Создание необходимых директорий

```bash
mkdir -p uploads domains_summary
```

### 3. Настройка окружения

Создайте файл `.env` в корне проекта (опционально):

```env
# Настройки для embedding модели
EMBEDDING_MODEL_URL=http://172.17.0.1:8089

# Настройки OpenAI API (если используете локальный сервер)
OPENAI_BASE_URL=http://172.17.0.1:19000/v1
OPENAI_API_KEY=your-api-key

# Настройки Qdrant
QDRANT_URL=http://qdrant-domains:6333
```

### 4. Запуск сервисов

```bash
docker-compose -f docker-compose-domains.yml up --build
```

### 5. Проверка работоспособности

После запуска сервисы будут доступны по следующим адресам:

- **Qdrant Dashboard**: http://localhost:6335
- **Indexing API**: http://localhost:8009
- **Agentic RAG API**: http://localhost:8663
- **MCP Server**: http://localhost:8007

## Конфигурация

### Порты сервисов

| Сервис | Внешний порт | Внутренний порт | Описание |
|--------|--------------|-----------------|----------|
| Qdrant | 6335 | 6333 | HTTP API |
| Qdrant | 6336 | 6334 | gRPC API |
| MCP Server | 8007 | 8000 | MCP протокол |
| Indexing API | 8009 | 8009 | REST API |
| Agentic RAG | 8663 | 8663 | REST API |

### Переменные окружения

#### Qdrant Domains
- Стандартные настройки Qdrant

#### MCP Server Qdrant
- `QDRANT_URL` - URL для подключения к Qdrant
- `COLLECTION_NAME` - имя коллекции (пустое значение позволяет выбирать коллекции)
- `EMBEDDING_PROVIDER` - провайдер эмбеддингов (tei/fastembed)
- `EMBEDDING_MODEL` - URL модели эмбеддингов

#### Indexing API
- `QDRANT_URL` - URL для подключения к Qdrant
- `EMBEDDING_MODEL_URL` - URL модели эмбеддингов
- `UPLOAD_DIR` - директория для загруженных файлов
- `DOMAINS_SUMMARY_DIR` - директория для сводок доменов
- `CHUNK_SIZE` - размер чанков для обработки

#### Agentic RAG
- `UPLOADS_PATH` - путь к загруженным файлам
- `SUMMARY_PATH` - путь к сводкам доменов
- `OPENAI_BASE_URL` - базовый URL для OpenAI API
- `OPENAI_API_KEY` - API ключ для OpenAI

## Использование

### 1. Индексация документов

Загрузите документы через Indexing API:

```bash
curl -X POST "http://localhost:8009/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your-document.pdf"
```

### 2. Поиск и генерация ответов

Используйте Agentic RAG API для поиска и генерации ответов:

```bash
curl -X POST "http://localhost:8663/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "ваш запрос"}'
```

### 3. Работа с MCP сервером

MCP сервер предоставляет интерфейс для работы с Qdrant через MCP протокол. Подключитесь к `http://localhost:8007`.

## Разработка

### Локальная разработка

Для локальной разработки установите зависимости:

```bash
# Indexing API
cd indexing_api
pip install -r requirements.txt

# Agentic RAG
cd ../agentic_rag
pip install -r requirements.txt

# MCP Server
cd ../mcp-server-qdrant
pip install -e .
```

### Структура проекта

```
agentic_rag/
├── agentic_rag/          # Основной сервис RAG
│   ├── Dockerfile
│   ├── qdrant_msp_use_agent.py
│   └── test_streaming_api.py
├── indexing_api/         # API для индексации документов
│   ├── Dockerfile
│   ├── indexing_api.py
│   ├── auth_api.py
│   ├── auth_jwt.py
│   ├── auth_models.py
│   └── file_parser.py
├── mcp-server-qdrant/    # MCP сервер для Qdrant
│   ├── Dockerfile
│   ├── src/
│   └── pyproject.toml
├── docker-compose-domains.yml
└── README.md
```

## Мониторинг и логи

Просмотр логов всех сервисов:

```bash
docker-compose -f docker-compose-domains.yml logs -f
```

Просмотр логов конкретного сервиса:

```bash
docker-compose -f docker-compose-domains.yml logs -f qdrant-domains
```

## Остановка сервисов

```bash
docker-compose -f docker-compose-domains.yml down
```

Для полной очистки (включая volumes):

```bash
docker-compose -f docker-compose-domains.yml down -v
```

## Устранение неполадок

### Проблемы с портами

Если порты заняты, измените их в `docker-compose-domains.yml`:

```yaml
ports:
  - "6336:6333"  # Измените внешний порт
```

### Проблемы с embedding моделью

Убедитесь, что embedding модель запущена и доступна по указанному URL:

```bash
curl http://172.17.0.1:8089/health
```

### Проблемы с правами доступа

Создайте необходимые директории с правильными правами:

```bash
sudo mkdir -p uploads domains_summary
sudo chown -R $USER:$USER uploads domains_summary
```

## Лицензия

Проект распространяется под лицензией MIT.

## Поддержка

При возникновении проблем создайте issue в репозитории GitHub.
