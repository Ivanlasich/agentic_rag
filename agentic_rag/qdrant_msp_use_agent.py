"""
FastAPI Streaming API для GraphRAG MCP Agent

Сервер с Server-Sent Events для streaming ответов от GraphRAG MCP агента.
"""

import asyncio
import json
import time
import os
import glob
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

# Загружаем переменные окружения
load_dotenv()

# Настройка переменных окружения для модели (переопределяемо через ENV)
os.environ.setdefault("OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", "http://172.17.0.1:19000/v1"))
os.environ.setdefault("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "dummy-key"))

# URL MCP сервера Qdrant (в Docker сети используем имя сервиса)
MCP_QDRANT_SSE_URL = os.getenv("MCP_QDRANT_SSE_URL", "http://mcp-qdrant-domains:8000/sse")

app = FastAPI(
    title="Qdrant Domains MCP Streaming API",
    description="API для streaming ответов от Qdrant Domains MCP агента с моделью Qwen3-Coder",
    version="1.0.0"
)

# Добавляем CORS middleware для веб-интерфейса
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальная переменная для кэширования агента
_agent_cache = None

# Пути к папкам с доменами (переопределяемо через ENV)
UPLOADS_PATH = os.getenv("UPLOADS_PATH", "/app/uploads")
SUMMARY_PATH = os.getenv("SUMMARY_PATH", "/app/domains_summary")

# Создаем директории (как в indexing_api.py)
os.makedirs(UPLOADS_PATH, exist_ok=True)
os.makedirs(SUMMARY_PATH, exist_ok=True)

def load_available_domains():
    """Загружает список доступных доменов из папки uploads"""
    domains = []
    uploads_dir = Path(UPLOADS_PATH)
    
    if uploads_dir.exists():
        for domain_dir in uploads_dir.iterdir():
            if domain_dir.is_dir():
                domains.append(domain_dir.name)
    return sorted(["tech_instruction", "client_interface","hr", "user_info"])
    return sorted(domains)

def load_domain_summary(domain_name: str) -> str:
    """Загружает summary для указанного домена"""
    summary_file = Path(SUMMARY_PATH) / f"{domain_name}_summary.txt"
    
    if summary_file.exists():
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"⚠️ Ошибка чтения summary для домена {domain_name}: {e}")
            return ""
    else:
        print(f"⚠️ Summary файл не найден для домена {domain_name}: {summary_file}")
        return ""

def load_all_domain_summaries():
    """Загружает все доступные summary доменов"""
    domains = load_available_domains()
    summaries = {}
    
    for domain in domains:
        summary = load_domain_summary(domain)
        if summary:
            summaries[domain] = summary
    
    return summaries

def build_domains_context():
    """Строит динамический контекст с информацией о всех доступных доменах для промпта"""
    domains = load_available_domains()
    summaries = load_all_domain_summaries()
    
    if not domains:
        return "\n## Доступные домены:\nДомены не найдены. Проверьте папку uploads.\n\n"
    
    context = "\n## Доступные домены и их описание:\n\n"
    
    # Добавляем информацию о каждом домене
    for domain in domains:
        context += f"### Домен: {domain}\n"
        
        if domain in summaries and summaries[domain]:
            context += f"{summaries[domain]}\n\n"
        else:
            context += f"Описание домена '{domain}' не найдено в summary файлах.\n\n"
    
    # Динамически строим инструкции на основе доступных доменов
    context += "## Инструкции по использованию доменов:\n"
    context += "- Используйте параметр `collection_name` для указания конкретного домена\n"
    context += f"- Доступные домены: {', '.join(domains)}\n"
    
    # Добавляем примеры для каждого домена
    context += "- Примеры правильных вызовов:\n"
    for domain in domains[:3]:  # Показываем примеры для первых 3 доменов
        context += f"  - `qdrant-find(query=\"ваш запрос\", collection_name=\"{domain}\")`\n"
    
    if len(domains) > 3:
        context += f"  - ... и другие домены: {', '.join(domains[3:])}\n"
    
    context += "\n"
    
    return context

def detect_hallucination(response_text: str) -> bool:
    """Детекция галлюцинаций в ответе агента"""
    if not response_text:
        return True
    
    # Признаки галлюцинаций
    hallucination_indicators = [
        "<tool_call>",
        "tool_call",
        "mcp_qdrant",
        "qdrant-find(",
        "qdrant-store("
    ]
    
    response_lower = response_text.lower()
    for indicator in hallucination_indicators:
        if indicator.lower() in response_lower:
            return True
    
    # Проверяем, что ответ содержит полезную информацию
    if len(response_text.strip()) < 50:
        return True
    
    # Проверяем, что ответ не содержит только технические ошибки
    if any(tech_word in response_lower for tech_word in ["error", "ошибка", "exception", "traceback"]):
        if not any(good_word in response_lower for good_word in ["ответ", "информация", "данные", "результат", "найдено"]):
            return True
    
    return False

# Pydantic модели для запросов
class ChatRequest(BaseModel):
    query: str

class StreamRequest(BaseModel):
    query: str

class ChatWithRetryRequest(BaseModel):
    query: str
    temperature: float = 0.1


async def create_agent():
    """Создание и кэширование MCP агента"""
    global _agent_cache
    
    if _agent_cache is not None:
        return _agent_cache
    
    try:
        # Конфигурация Qdrant Domains MCP сервера
        config = {
            "mcpServers": {
                "qdrant-domains": {
                    "url": MCP_QDRANT_SSE_URL
                }
            }
        }
        
        client = MCPClient.from_dict(config)
        
        llm = ChatOpenAI(
            model="Qwen/Qwen3-Coder-30B-A3B-Instruct",
            base_url=os.environ["OPENAI_BASE_URL"],
            api_key="dummy-key",
            temperature=0.3,
            max_tokens=2000
        )
    
        # Создаем агента с MCP клиентом
        agent = MCPAgent(
            llm=llm,
            client=client,
            max_steps=2,
            verbose=True,  # Включаем подробный вывод
            memory_enabled=True  # Включаем память разговора
        )
        
        # Инициализируем агента
        #await agent.initialize()
        
        print("✅ Qdrant Domains MCP Agent инициализирован")
        return agent
        
    except Exception as e:
        print(f"❌ Ошибка создания агента: {e}")
        raise e


@app.post("/stream")
async def stream_agent_response(request: StreamRequest):
    """Stream agent response using Server-Sent Events"""
    
    async def event_generator():
        try:
            system_prompt = """
# Системный промпт для агента с Qdrant Domains

## Роль и назначение
Вы - специализированный агент-ассистент, работающий с векторной базой данных Qdrant Domains. Ваша основная задача - предоставлять точные и релевантные ответы на основе информации, хранящейся в векторной базе данных с поддержкой доменов.

## Инструменты поиска
У вас есть доступ к инструментам:

### `qdrant-find`
- **Назначение**: Поиск информации в векторной базе данных по доменам
- **Применение**: Используйте для поиска релевантных документов, фрагментов текста или данных по любому запросу
- **Особенности**: 
  - Поддерживает семантический поиск по доменам
  - Возвращает наиболее релевантные результаты
  - Может искать по ключевым словам, фразам или концепциям
  - Поддерживает поиск по различным коллекциям доменов

### `qdrant-store`
- **Назначение**: Сохранение информации в векторную базу данных
- **Применение**: Используйте для сохранения важной информации для последующего поиска
- **Особенности**:
  - Позволяет сохранять текстовую информацию
  - Автоматически создает векторные представления
  - Поддерживает метаданные для лучшей организации

## Правила работы

### 1. **КРИТИЧЕСКИ ВАЖНО: Формат вызова инструментов**
- ВСЕГДА используйте ТОЛЬКО JSON-формат для вызова инструментов
- НЕ используйте XML-подобный синтаксис типа `<function=name> <parameter=key>value</parameter> </function>`
- ПРАВИЛЬНЫЙ формат: вызывайте инструменты как функции с JSON-аргументами
- Пример ПРАВИЛЬНОГО вызова: `qdrant-find(query="ваш запрос", collection_name="имя_коллекции")`
- Пример НЕПРАВИЛЬНОГО: `<function=qdrant-find> <parameter=query>ваш запрос</parameter> </function>`

### 2. Приоритет поиска
- **ВСЕГДА** начинайте с поиска в базе данных перед формулированием ответа
- Используйте `qdrant-find` для каждого запроса, даже если кажется, что ответ очевиден
- Если поиск не дал результатов, сообщите об этом пользователю
- Попробуйте поиск в разных коллекциях доменов

### 3. Стратегия поиска
- Используйте различные формулировки запросов для получения полной картины
- Разбивайте сложные вопросы на более простые поисковые запросы
- Комбинируйте результаты нескольких поисковых запросов
- Пробуйте синонимы и альтернативные формулировки
- Экспериментируйте с разными коллекциями доменов

### 4. Качество ответов
- Отвечайте ТОЛЬКО на основе найденной в базе данных информации
- Если информации недостаточно, честно сообщите об этом
- Не выдумывайте и не предполагайте информацию, которой нет в базе
- Цитируйте конкретные фрагменты из найденных документов

## Примеры использования

### ПРАВИЛЬНЫЙ формат вызова инструментов:

**✅ ПРАВИЛЬНО - JSON-формат:**
```
qdrant-find(query="система авторизации", collection_name="cliring")
```

**❌ НЕПРАВИЛЬНО - XML-формат:**
```
<function=qdrant-find> <parameter=query>система авторизации</parameter> </function>
```

### Поиск информации
```
Пользователь: "Как работает система авторизации?"
Действие: Используйте qdrant-find с запросом "система авторизации" и collection_name="cliring"
```

### Множественный поиск
```
Пользователь: "Какие есть методы для работы с клиентскими счетами?"
Действие: 
1. qdrant-find(query="клиентские счета", collection_name="cliring")
2. qdrant-find(query="методы работы счетами", collection_name="cliring")
3. qdrant-find(query="управление счетами", collection_name="cliring")
```

### Поиск в разных доменах
```
Пользователь: "Информация о пользователях"
Действие: 
1. qdrant-find(query="пользователи", collection_name="cliring")
2. qdrant-find(query="пользователи", collection_name="other_domain")
```

## Ограничения
- НЕ используйте внешние источники информации
- НЕ генерируйте ответы на основе общих знаний
- НЕ предполагайте информацию, которой нет в базе данных
- ВСЕГДА указывайте источник информации (найденные документы и коллекцию)

## Формат ответов
1. Выполните поиск в базе данных (укажите коллекцию)
2. Проанализируйте найденные результаты
3. Сформулируйте ответ на основе найденной информации
4. Укажите источники информации и коллекцию

## Советы по эффективному поиску
- Используйте конкретные термины из предметной области
- Пробуйте как общие, так и специфические запросы
- Если первый поиск не дал результатов, попробуйте другие формулировки
- Для сложных вопросов делайте несколько поисковых запросов
- Экспериментируйте с разными коллекциями доменов
- Используйте qdrant-store для сохранения важной информации

Помните: ваша ценность заключается в точном поиске и предоставлении информации из индексированной базы данных с поддержкой доменов, а не в генерации ответов на основе общих знаний.
ОБРАТИ ВНИМАНИЕ НА ФОРМАТ ВЫЗОВА ИНСТРУМЕНТОВ - ОН ДОЛЖЕН БЫТЬ ОЧЕНЬ ТОЧНЫМ.
Ответ должен быть строго на РУССКОМ ЯЗЫКЕ
Ты никогда не можешь заканчивать на step 1 - значит ты неверно вызвал tool
"""
            
            # Добавляем информацию о доступных доменах
            domains_context = build_domains_context()
            system_prompt += domains_context
            #qdrant_query = f"""При вызове инструментов обязательно перепроверь формат вызова инструментов. Инструменты qdrant-domains позволяют осуществлять поиск в векторной базе данных с поддержкой доменов, в которой содержатся ответы на все вопросы пользователя. Используй все доступные поисковые инструменты (qdrant-find и qdrant-store) для поиска чтобы дать правильный ответ на следующий вопрос: {request.query}"""
            # Получаем доступные домены для использования в запросе
            available_domains = load_available_domains()
            
            if available_domains:
                domains_list = ", ".join(available_domains)
                examples = "\n".join([f"- qdrant-find(query=\"ваш запрос\", collection_name=\"{domain}\")" for domain in available_domains[:3]])
                if len(available_domains) > 3:
                    examples += f"\n- ... и другие домены: {', '.join(available_domains[3:])}"
            else:
                domains_list = "домены не найдены"
                examples = "- qdrant-find(query=\"ваш запрос\", collection_name=\"default\")"
            
            qdrant_query = f"""ИСПОЛЬЗУЙТЕ ТОЛЬКО JSON-формат при вызове инструментов. 
Доступные домены: {domains_list}
Примеры правильных вызовов:
{examples}

Ответь на следующий вопрос: {request.query}"""
            #graphrag_query = f"""У тебя возникают проблемы при вызове инструментов ОБЯЗАТЕЛЬНО ПОДУМАЙ И ПРОВЕРЬ ФОРМАТ вызова инструментов - вызывай инструменты так `mcp_qdrant_qdrant-find(query="ваш запрос")`. Инструменты qdrant позваляют осуществлять поиск в индексированной базе знаний в которой содержаться ответы на все вопросы пользователя, на данный момент используй все доступные поисковые инструменты для поиска, чтобы дать правильный ответ на следующий вопрос: {request.query}"""

            # Массив температур для повторных попыток
            temperature_values = [0.2, 1, 2, 3, 4]
            max_attempts = len(temperature_values)
            
            # Отправляем начальное событие
            yield f"data: {json.dumps({'type': 'start', 'message': 'Начинаем обработку запроса с системой повторных попыток...', 'query': request.query, 'max_attempts': max_attempts, 'timestamp': time.time()})}\n\n"
            
            import mcp_use
            config = {
                "mcpServers": {
                    "qdrant-domains": {
                        "url": MCP_QDRANT_SSE_URL
                    }
                }
            }
            client = MCPClient.from_dict(config)
           
            await client.create_all_sessions()
            session = client.get_session("qdrant-domains")
                
            if session:
                tools = await session.list_tools()
                # Отправляем информацию об инструментах
                yield f"data: {json.dumps({'type': 'tools_info', 'message': f'Найдено {len(tools)} инструментов', 'tools': [{'name': tool.name, 'description': tool.description} for tool in tools], 'timestamp': time.time()})}\n\n"
            
            # Перебираем попытки с разными температурами
            final_result = None
            for attempt in range(max_attempts):
                temperature = temperature_values[attempt]
                
                yield f"data: {json.dumps({'type': 'attempt_start', 'message': f'Попытка {attempt + 1}/{max_attempts} с температурой {temperature}', 'attempt': attempt + 1, 'temperature': temperature, 'timestamp': time.time()})}\n\n"
                
                # Создаем LLM с настройками для Qwen3-Coder
                llm = ChatOpenAI(
                    model="Qwen/Qwen3-Coder-30B-A3B-Instruct",
                    base_url=os.environ["OPENAI_BASE_URL"],
                    api_key="dummy-key",
                    temperature=temperature,
                    max_tokens=2000
                )
            
                # Создаем агента с MCP клиентом
                agent = MCPAgent(
                    llm=llm,
                    client=client,
                    max_steps=20,
                    verbose=True,
                    memory_enabled=False,
                    additional_instructions=system_prompt
                )
                                            
                # Используем stream для получения детальных событий
                tool_results = []  # Собираем результаты инструментов
                
                async for item in agent.stream(qdrant_query):
                    if isinstance(item, str):
                        # Final result
                        final_result = item
                        is_hallucination = detect_hallucination(final_result)
                        print(f"🔧 Галлюцинация: {is_hallucination}")
                        if is_hallucination == True:
                            #final_result = None
                            break
                        else:
                            yield f"data: {json.dumps({'type': 'final_result', 'message': f'Получен финальный результат на попытке {attempt + 1}', 'content': item, 'attempt': attempt + 1, 'temperature': temperature, 'timestamp': time.time()})}\n\n"
                            break  # Выходим из цикла при получении финального результата
                    else:
                        # Intermediate step (action, observation)
                        action, observation = item
                        print(f'Вызов инструмента: {action.tool}')
                        yield f"data: {json.dumps({'type': 'tool_call', 'message': f'Вызов инструмента: {action.tool}', 'tool': action.tool, 'tool_input': str(action.tool_input) if hasattr(action, 'tool_input') else None, 'attempt': attempt + 1, 'timestamp': time.time()})}\n\n"
                        
                        # Сохраняем результат инструмента
                        tool_results.append({
                            'tool': action.tool,
                            'observation': observation,
                            'tool_input': str(action.tool_input) if hasattr(action, 'tool_input') else None
                        })
                        
                        # Оставляем только последние 5 результатов
                        if len(tool_results) > 5:
                            tool_results = tool_results[-5:]
                        
                        # Отправляем результат инструмента
                        yield f"data: {json.dumps({'type': 'tool_result', 'message': 'Результат выполнения инструмента', 'observation': observation[:500] + ('...' if len(observation) > 500 else ''), 'attempt': attempt + 1, 'timestamp': time.time()})}\n\n"
                
                # Проверяем результат на галлюцинации
                if final_result:                    
                    hallucination_status = "Да" if is_hallucination else "Нет"
                    yield f"data: {json.dumps({'type': 'hallucination_check', 'message': f'Проверка на галлюцинации: {hallucination_status}', 'is_hallucination': is_hallucination, 'attempt': attempt + 1, 'timestamp': time.time()})}\n\n"
                    
                    if not is_hallucination:
                        # Успешный результат без галлюцинаций
                        yield f"data: {json.dumps({'type': 'success', 'message': f'Успешный ответ получен на попытке {attempt + 1}', 'attempt': attempt + 1, 'temperature': temperature, 'timestamp': time.time()})}\n\n"
                        break  # Выходим из цикла попыток
                    else:
                        # Обнаружена галлюцинация
                        yield f"data: {json.dumps({'type': 'hallucination_detected', 'message': f'Обнаружена галлюцинация на попытке {attempt + 1}', 'attempt': attempt + 1, 'temperature': temperature, 'timestamp': time.time()})}\n\n"
                        
                        if attempt < max_attempts - 1:
                            yield f"data: {json.dumps({'type': 'retry', 'message': f'Переходим к попытке {attempt + 2} с температурой {temperature_values[attempt + 1]}', 'next_temperature': temperature_values[attempt + 1], 'timestamp': time.time()})}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'all_attempts_failed', 'message': 'Все попытки исчерпаны, принудительно генерируем ответ', 'timestamp': time.time()})}\n\n"
                else:
                    # Если не получили финальный результат, принудительно генерируем ответ
                    yield f"data: {json.dumps({'type': 'forced_generation', 'message': f'Агент не дал финальный результат на попытке {attempt + 1}. Принудительно генерируем ответ...', 'attempt': attempt + 1, 'timestamp': time.time()})}\n\n"
                    
                    if tool_results:
                        # Создаем контекст из последних 5 результатов инструментов
                        context_parts = []
                        for i, result in enumerate(tool_results, 1):
                            context_parts.append(f"Результат {i} ({result['tool']}):\n{result['observation']}\n")
                        
                        context = "\n".join(context_parts)
                        
                        # Создаем промпт для принудительной генерации ответа
                        forced_prompt = f"""На основе результатов поиска в векторной базе данных Qdrant Domains, дай полный ответ на вопрос пользователя.

Вопрос пользователя: {request.query}

Результаты поиска:
{context}

Требования к ответу:
1. Дай полный и структурированный ответ на основе найденной информации
2. Если информации недостаточно, честно об этом сообщи
3. Используй только информацию из результатов поиска
4. Структурируй ответ логично и понятно
5. Укажи, что ответ основан на данных из Qdrant Domains

Ответ:"""

                        try:
                            # Создаем отдельный LLM для генерации ответа
                            forced_llm = ChatOpenAI(
                                model="Qwen/Qwen3-Coder-30B-A3B-Instruct",
                                base_url=os.environ["OPENAI_BASE_URL"],
                                api_key="dummy-key",
                                temperature=0.2,
                                max_tokens=2000
                            )
                            
                            # Генерируем ответ
                            response = await forced_llm.ainvoke(forced_prompt)
                            final_result = response.content if hasattr(response, 'content') else str(response)
                            
                            yield f"data: {json.dumps({'type': 'forced_result', 'message': 'Принудительно сгенерированный ответ на основе результатов поиска', 'content': final_result, 'attempt': attempt + 1, 'timestamp': time.time()})}\n\n"
                            
                            # Проверяем принудительно сгенерированный ответ на галлюцинации
                            is_hallucination = detect_hallucination(final_result)
                            
                            if not is_hallucination:
                                yield f"data: {json.dumps({'type': 'final_result', 'message': f'Принудительно сгенерированный ответ успешен на попытке {attempt + 1}', 'attempt': attempt + 1, 'temperature': temperature, 'timestamp': time.time()})}\n\n"
                                break  # Выходим из цикла попыток
                            else:
                                yield f"data: {json.dumps({'type': 'forced_hallucination', 'message': f'Принудительно сгенерированный ответ содержит галлюцинации на попытке {attempt + 1}', 'attempt': attempt + 1, 'timestamp': time.time()})}\n\n"
                                
                        except Exception as forced_error:
                            print(f"Ошибка при принудительной генерации ответа: {forced_error}")
                            # Fallback ответ
                            fallback_response = f"""На основе проведенного поиска в векторной базе данных Qdrant Domains по запросу "{request.query}":

{context[:1000]}...

Выполнено {len(tool_results)} поисковых запросов, но не удалось сформировать полный ответ.

Рекомендации:
1. Попробуйте переформулировать вопрос
2. Используйте более конкретные термины
3. Разбейте сложный вопрос на части

На основе данных из Qdrant Domains."""
                            
                            final_result = fallback_response
                            yield f"data: {json.dumps({'type': 'fallback_result', 'message': 'Fallback ответ на основе результатов поиска', 'content': final_result, 'attempt': attempt + 1, 'timestamp': time.time()})}\n\n"
                            break  # Выходим из цикла попыток
                    else:
                        # Если вообще нет результатов
                        no_results_response = f"""Не удалось выполнить поиск в векторной базе данных Qdrant Domains по запросу "{request.query}".

Возможные причины:
- Проблемы с подключением к базе данных
- Ошибки в работе инструментов поиска
- Недоступность сервиса

Попробуйте повторить запрос позже или обратитесь к администратору."""
                        
                        final_result = no_results_response
                        yield f"data: {json.dumps({'type': 'no_results', 'message': 'Ответ при отсутствии результатов поиска', 'content': final_result, 'attempt': attempt + 1, 'timestamp': time.time()})}\n\n"
                        break  # Выходим из цикла попыток
            
            # Отправляем завершающее событие
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Обработка завершена', 'final_result': final_result, 'timestamp': time.time()})}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            error_data = {"type": "error", "message": f"Ошибка: {str(e)}", "timestamp": time.time()}
            yield f"data: {json.dumps(error_data)}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )


@app.post("/chat")
async def chat_response(request: ChatRequest, temperature: float = 0.3):
    """Chat endpoint с логикой как у /stream: ретраи, проверка галлюцинаций, принудительная генерация"""
    try:
        # Системный промпт как в /stream
        system_prompt = """
# Системный промпт для агента с Qdrant Domains

## Роль и назначение
Вы - специализированный агент-ассистент, работающий с векторной базой данных Qdrant Domains. Ваша основная задача - предоставлять точные и релевантные ответы на основе информации, хранящейся в векторной базе данных с поддержкой доменов.

## Инструменты поиска
У вас есть доступ к инструментам:

### `qdrant-find`
- **Назначение**: Поиск информации в векторной базе данных по доменам
- **Применение**: Используйте для поиска релевантных документов, фрагментов текста или данных по любому запросу
- **Особенности**: 
  - Поддерживает семантический поиск по доменам
  - Возвращает наиболее релевантные результаты
  - Может искать по ключевым словам, фразам или концепциям
  - Поддерживает поиск по различным коллекциям доменов

### `qdrant-store`
- **Назначение**: Сохранение информации в векторную базу данных
- **Применение**: Используйте для сохранения важной информации для последующего поиска
- **Особенности**:
  - Позволяет сохранять текстовую информацию
  - Автоматически создает векторные представления
  - Поддерживает метаданные для лучшей организации

## Правила работы

### 1. **КРИТИЧЕСКИ ВАЖНО: Формат вызова инструментов**
- ВСЕГДА используйте ТОЛЬКО JSON-формат для вызова инструментов
- НЕ используйте XML-подобный синтаксис типа `<function=name> <parameter=key>value</parameter> </function>`
- ПРАВИЛЬНЫЙ формат: вызывайте инструменты как функции с JSON-аргументами
- Пример ПРАВИЛЬНОГО вызова: `qdrant-find(query="ваш запрос", collection_name="имя_коллекции")`
- Пример НЕПРАВИЛЬНОГО: `<function=qdrant-find> <parameter=query>ваш запрос</parameter> </function>`

### 2. Приоритет поиска
- **ВСЕГДА** начинайте с поиска в базе данных перед формулированием ответа
- Используйте `qdrant-find` для каждого запроса, даже если кажется, что ответ очевиден
- Если поиск не дал результатов, сообщите об этом пользователю
- Попробуйте поиск в разных коллекциях доменов

### 3. Стратегия поиска
- Используйте различные формулировки запросов для получения полной картины
- Разбивайте сложные вопросы на более простые поисковые запросы
- Комбинируйте результаты нескольких поисковых запросов
- Пробуйте синонимы и альтернативные формулировки
- Экспериментируйте с разными коллекциями доменов

### 4. Качество ответов
- Отвечайте ТОЛЬКО на основе найденной в базе данных информации
- Если информации недостаточно, честно сообщите об этом
- Не выдумывайте и не предполагайте информацию, которой нет в базе
- Цитируйте конкретные фрагменты из найденных документов

## Примеры использования

### ПРАВИЛЬНЫЙ формат вызова инструментов:

**✅ ПРАВИЛЬНО - JSON-формат:**
```
qdrant-find(query="система авторизации", collection_name="cliring")
```

**❌ НЕПРАВИЛЬНО - XML-формат:**
```
<function=qdrant-find> <parameter=query>система авторизации</parameter> </function>
```

### Поиск информации
```
Пользователь: "Как работает система авторизации?"
Действие: Используйте qdrant-find с запросом "система авторизации" и collection_name="cliring"
```

### Множественный поиск
```
Пользователь: "Какие есть методы для работы с клиентскими счетами?"
Действие: 
1. qdrant-find(query="клиентские счета", collection_name="cliring")
2. qdrant-find(query="методы работы счетами", collection_name="cliring")
3. qdrant-find(query="управление счетами", collection_name="cliring")
```

### Поиск в разных доменах
```
Пользователь: "Информация о пользователях"
Действие: 
1. qdrant-find(query="пользователи", collection_name="cliring")
2. qdrant-find(query="пользователи", collection_name="other_domain")
```

## Ограничения
- НЕ используйте внешние источники информации
- НЕ генерируйте ответы на основе общих знаний
- НЕ предполагайте информацию, которой нет в базе данных
- ВСЕГДА указывайте источник информации (найденные документы и коллекцию)

## Формат ответов
1. Выполните поиск в базе данных (укажите коллекцию)
2. Проанализируйте найденные результаты
3. Сформулируйте ответ на основе найденной информации
4. Укажите источники информации и коллекцию

## Советы по эффективному поиску
- Используйте конкретные термины из предметной области
- Пробуйте как общие, так и специфические запросы
- Если первый поиск не дал результатов, попробуйте другие формулировки
- Для сложных вопросов делайте несколько поисковых запросов
- Экспериментируйте с разными коллекциями доменов
- Используйте qdrant-store для сохранения важной информации

Помните: ваша ценность заключается в точном поиске и предоставлении информации из индексированной базы данных с поддержкой доменов, а не в генерации ответов на основе общих знаний.
ОБРАТИ ВНИМАНИЕ НА ФОРМАТ ВЫЗОВА ИНСТРУМЕНТОВ - ОН ДОЛЖЕН БЫТЬ ОЧЕНЬ ТОЧНЫМ.
Ответ должен быть строго на РУССКОМ ЯЗЫКЕ
Ты никогда не можешь заканчивать на step 1 - значит ты неверно вызвал tool
"""
        # Динамический контекст доменов
        domains_context = build_domains_context()
        system_prompt += domains_context

        # Доступные домены и примеры
        available_domains = load_available_domains()
        if available_domains:
            domains_list = ", ".join(available_domains)
            examples = "\n".join([f"- qdrant-find(query=\"ваш запрос\", collection_name=\"{d}\")" for d in available_domains[:3]])
            if len(available_domains) > 3:
                examples += f"\n- ... и другие домены: {', '.join(available_domains[3:])}"
        else:
            domains_list = "домены не найдены"
            examples = "- qdrant-find(query=\"ваш запрос\", collection_name=\"default\")"

        qdrant_query = f"""ИСПОЛЬЗУЙТЕ ТОЛЬКО JSON-формат при вызове инструментов. 
Доступные домены: {domains_list}
Примеры правильных вызовов:
{examples}

Ответь на следующий вопрос: {request.query}"""

        # MCP клиент и инструменты
        config = {
            "mcpServers": {
                "qdrant-domains": {"url": MCP_QDRANT_SSE_URL}
            }
        }
        client = MCPClient.from_dict(config)
        await client.create_all_sessions()
        session = client.get_session("qdrant-domains")
        if session:
            try:
                tools = await session.list_tools()
                print(f"🔧 Найдено {len(tools)} инструментов для /chat")
            except Exception:
                pass

        # Температуры как в /stream
        temperature_values = [0.2, 1, 2, 3, 4]
        max_attempts = len(temperature_values)

        last_response_text = None
        last_tool_results = []

        for attempt in range(max_attempts):
            current_temp = temperature_values[attempt]
            print(f"🔧 Попытка {attempt + 1} из {max_attempts}, температура: {current_temp}")
            # LLM и агент
            llm = ChatOpenAI(
                model="Qwen/Qwen3-Coder-30B-A3B-Instruct",
                base_url=os.environ["OPENAI_BASE_URL"],
                api_key="dummy-key",
                temperature=current_temp,
                max_tokens=2000
            )

            agent = MCPAgent(
                llm=llm,
                client=client,
                max_steps=20,
                verbose=True,
                memory_enabled=False,
                additional_instructions=system_prompt
            )

            tool_results = []
            final_result = None

            async for item in agent.stream(qdrant_query):
                if isinstance(item, str):
                    final_result = item
                    print(f"🔧 Результат: {final_result}")
                    is_hallucination = detect_hallucination(final_result)
                    print(f"🔧 Галлюцинация: {is_hallucination}")
                    if is_hallucination:
                        print(f"Зашли в галлюцинацию: {is_hallucination}")
                        last_response_text = final_result
                        last_tool_results = tool_results
                        final_result = None
                        break
                    else:
                        return {
                            "query": request.query,
                            "response": final_result,
                            "attempt": attempt + 1,
                            "total_attempts": max_attempts,
                            "temperature": current_temp,
                            "tool_calls_count": len(tool_results),
                            "hallucination_detected": False,
                            "timestamp": time.time()
                        }
                else:
                    action, observation = item
                    tool_results.append({
                        'tool': action.tool,
                        'observation': observation,
                        'tool_input': str(action.tool_input) if hasattr(action, 'tool_input') else None
                    })
                    if len(tool_results) > 5:
                        tool_results = tool_results[-5:]

            # Если финальный результат отсутствует — принудительная генерация на основе tool_results
            if not final_result:
                print(f"🔧 Нет финального результата, принудительная генерация: {tool_results}")
                print(f"🔧 Tool results: {tool_results}")
                if len(tool_results) > 0:
                    context_parts = []
                    for i, result in enumerate(tool_results, 1):
                        context_parts.append(f"Результат {i} ({result['tool']}):\n{result['observation']}\n")
                    context = "\n".join(context_parts)

                    forced_prompt = f"""На основе результатов поиска в векторной базе данных Qdrant Domains, дай полный ответ на вопрос пользователя.

Вопрос пользователя: {request.query}

Результаты поиска:
{context}

Требования к ответу:
1. Дай полный и структурированный ответ на основе найденной информации
2. Если информации недостаточно, честно об этом сообщи
3. Используй только информацию из результатов поиска
4. Структурируй ответ логично и понятно
5. Укажи, что ответ основан на данных из Qdrant Domains

Ответ:"""

                    try:
                        forced_llm = ChatOpenAI(
                            model="Qwen/Qwen3-Coder-30B-A3B-Instruct",
                            base_url=os.environ["OPENAI_BASE_URL"],
                            api_key="dummy-key",
                            temperature=0.2,
                            max_tokens=2000
                        )
                        response = await forced_llm.ainvoke(forced_prompt)
                        forced_text = response.content if hasattr(response, 'content') else str(response)
                        is_hallucination = detect_hallucination(forced_text)
                        if not is_hallucination:
                            return {
                                "query": request.query,
                                "response": forced_text,
                                "attempt": attempt + 1,
                                "total_attempts": max_attempts,
                                "temperature": current_temp,
                                "tool_calls_count": len(tool_results),
                                "forced_generation": True,
                                "hallucination_detected": False,
                                "timestamp": time.time()
                            }
                        else:
                            last_response_text = forced_text
                            last_tool_results = tool_results
                    except Exception as forced_error:
                        print(f"Ошибка при принудительной генерации ответа: {forced_error}")
                        # Переходим к следующей попытке
                        last_response_text = last_response_text or ""
                        last_tool_results = tool_results or last_tool_results
                else:
                    # Совсем нет результатов инструментов
                    continue
                    no_results_response = f"""Не удалось выполнить поиск в векторной базе данных Qdrant Domains по запросу "{request.query}".

Возможные причины:
- Проблемы с подключением к базе данных
- Ошибки в работе инструментов поиска
- Недоступность сервиса

Попробуйте повторить запрос позже или обратитесь к администратору."""
                    return {
                        "query": request.query,
                        "response": no_results_response,
                        "attempt": attempt + 1,
                        "total_attempts": max_attempts,
                        "temperature": current_temp,
                        "tool_calls_count": 0,
                        "hallucination_detected": False,
                        "timestamp": time.time()
                    }

        # Если все попытки не дали качественного результата
        return {
            "query": request.query,
            "response": last_response_text or "Все попытки не дали качественного результата.",
            "attempt": max_attempts,
            "total_attempts": max_attempts,
            "temperature": temperature_values[-1],
            "tool_calls_count": len(last_tool_results),
            "hallucination_detected": True,
            "warning": "Все попытки исчерпаны, ответ может содержать галлюцинации",
            "timestamp": time.time()
        }

    except Exception as e:
        print(f"Ошибка в chat endpoint: {e}")
        return {
            "query": request.query,
            "response": f"Ошибка при обработке запроса: {str(e)}",
            "error": str(e),
            "timestamp": time.time()
        }

@app.get("/tools")
async def get_available_tools():
    """Получение списка доступных инструментов"""
    try:
        agent = await create_agent()
        client = agent.client
        
        # Получаем инструменты
        await client.create_all_sessions()
        session = client.get_session("qdrant-domains")
        
        if session:
            tools = await session.list_tools()
            return {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema if hasattr(tool, 'inputSchema') else None
                    }
                    for tool in tools
                ],
                "count": len(tools),
                "timestamp": time.time()
            }
        else:
            return {"error": "Не удалось получить сессию", "timestamp": time.time()}
            
    except Exception as e:
        return {"error": str(e), "timestamp": time.time()}


@app.get("/domains")
async def get_domains():
    """Получение списка доступных доменов и их описаний"""
    try:
        domains = load_available_domains()
        summaries = load_all_domain_summaries()
        
        domains_info = []
        for domain in domains:
            domain_info = {
                "name": domain,
                "summary": summaries.get(domain, ""),
                "has_summary": domain in summaries
            }
            domains_info.append(domain_info)
        
        return {
            "domains": domains_info,
            "count": len(domains),
            "uploads_path": UPLOADS_PATH,
            "summary_path": SUMMARY_PATH,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": time.time()
        }

@app.get("/status")
async def get_status():
    """Проверка статуса сервера и агента"""
    try:
        agent = await create_agent()
        domains = load_available_domains()
        return {
            "status": "ok",
            "agent_initialized": True,
            "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
            "api_url": "http://localhost:19000/v1",
            "mcp_server": "http://localhost:8007/sse",
            "available_domains": domains,
            "domains_count": len(domains),
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": time.time()
        }


@app.get("/")
async def root():
    """Главная страница API"""
    domains = load_available_domains()
    summaries = load_all_domain_summaries()
    
    return {
        "message": "Qdrant Domains MCP Streaming API",
        "version": "1.0.0",
        "endpoints": {
            "stream": "POST /stream - Streaming ответы с поддержкой доменов",
            "chat": "POST /chat - Обычные ответы с поддержкой доменов", 
            "chat-with-retry": "POST /chat-with-retry - Ответы с повторными попытками при галлюцинациях",
            "tools": "GET /tools - Список инструментов",
            "domains": "GET /domains - Список доступных доменов",
            "status": "GET /status - Статус сервера"
        },
        "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
        "mcp_server": "http://localhost:8007/sse",
        "domains": {
            "available": domains,
            "count": len(domains),
            "with_summaries": len(summaries),
            "uploads_path": UPLOADS_PATH,
            "summary_path": SUMMARY_PATH
        },
        "timestamp": time.time()
    }


# Простая обработка shutdown (для совместимости)
import atexit

def cleanup():
    """Очистка ресурсов при завершении"""
    global _agent_cache
    if _agent_cache and hasattr(_agent_cache, 'client'):
        try:
            # Создаем event loop для cleanup
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_agent_cache.client.close_all_sessions())
            loop.close()
            print("🧹 Ресурсы очищены")
        except Exception as e:
            print(f"⚠️ Ошибка при очистке ресурсов: {e}")

atexit.register(cleanup)


if __name__ == "__main__":
    import uvicorn
    print("🚀 Запуск Qdrant Domains MCP Streaming API...")
    print("📡 Модель: Qwen/Qwen3-Coder-30B-A3B-Instruct")
    print("🔗 MCP сервер: http://localhost:8007/sse")
    print("🌐 API будет доступен на: http://0.0.0.0:8663")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8663,
        log_level="info"
    )
