#!/usr/bin/env python3
"""
Простой тест для FastAPI Streaming API с Qdrant Domains
"""

import asyncio
import aiohttp
import json
import time

async def test_streaming_api():
    """Тест streaming API с обработкой ответов по типам"""
    
    # URL API сервера
    api_url = "http://localhost:8663/stream"
    
    # Тестовый запрос
    #test_query = "Основные проблемы в клиринге на данный момент?"
    #test_query = "Основные проблемы в клиринге на данный момент?"
    test_query = "Расскажи про маски логинов на срочном рынке?"
    test_query = "Как расшифровывается маски логинов на срочном рынке?"

    
    print(f"🚀 Тестируем streaming API...")
    print(f"📡 URL: {api_url}")
    print(f"❓ Запрос: {test_query}")
    print("-" * 50)
    
    # Данные для запроса
    request_data = {
        "query": test_query
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status != 200:
                    print(f"❌ Ошибка HTTP: {response.status}")
                    return
                
                print(f"✅ Подключение установлено (статус: {response.status})")
                print("📡 Начинаем получение streaming данных...")
                print("-" * 50)
                
                # Читаем streaming ответ
                async for line in response.content:
                    line_str = line.decode('utf-8').strip()
                    
                    if not line_str:
                        continue
                    
                    # Пропускаем служебные строки SSE
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Убираем 'data: '
                        
                        if data_str == '[DONE]':
                            print("🏁 Получен сигнал завершения")
                            break
                        
                        try:
                            # Парсим JSON данные
                            data = json.loads(data_str)
                            
                            # Обрабатываем по типу
                            event_type = data.get('type', 'unknown')
                            timestamp = data.get('timestamp', time.time())
                            
                            if event_type == 'start':
                                print(f"🚀 {data.get('message', '')}")
                                print(f"   Запрос: {data.get('query', '')}")
                                
                            elif event_type == 'tools_info':
                                tools_count = data.get('tools', [])
                                print(f"🔧 Найдено инструментов: {len(tools_count)}")
                                for tool in tools_count:
                                    print(f"   - {tool.get('name', '')}: {tool.get('description', '')}")
                                    
                            elif event_type == 'tool_call':
                                tool_name = data.get('tool', 'unknown')
                                tool_input = data.get('tool_input', '')
                                print(f"🔨 Вызываю tool: {tool_name}")
                                if tool_input:
                                    print(f"   Параметры: {tool_input}")
                                    
                            elif event_type == 'tool_result':
                                observation = data.get('observation', '')
                                print(f"📋 Результат tool: {observation}")
                                
                            elif event_type == 'final_result':
                                content = data.get('content', '')
                                print(f"🎯 Финальный ответ:")
                                print(f"   {content}")
                                
                            elif event_type == 'complete':
                                print(f"✅ {data.get('message', '')}")
                                
                            elif event_type == 'error':
                                print(f"❌ Ошибка: {data.get('message', '')}")
                                
                            else:
                                print(f"❓ Неизвестный тип события: {event_type}")
                                print(f"   Данные: {data}")
                            
                            print()  # Пустая строка для разделения
                            
                        except json.JSONDecodeError as e:
                            print(f"⚠️ Ошибка парсинга JSON: {e}")
                            print(f"   Строка: {data_str}")
                            
                        except Exception as e:
                            print(f"⚠️ Ошибка обработки события: {e}")
                            print(f"   Данные: {data_str}")
    
    except aiohttp.ClientError as e:
        print(f"❌ Ошибка подключения: {e}")
        print("💡 Убедитесь, что API сервер запущен на порту 8663")
        
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")


async def test_simple_chat():
    """Тест простого chat endpoint"""
    
    api_url = "http://localhost:8663/chat"
    test_query = "Как расшифровывается маски логинов на срочном рынке?"
    test_query = "Дай мне ФИО Директора по развитию искусственного интеллекта в Мосбирже?"
    #test_query ="Дай мне ФИО Директора по инновационному развитию искусственного интеллекта в Мосбирже?"
    #test_query ="Мне нужна инфа о Наумов Даниил в Мосбирже?"
    #test_query ="Мне нужна инфа о Армен Амирханян в Мосбирже?"

    print(f"\n🚀 Тестируем простой chat API...")
    print(f"📡 URL: {api_url}")
    print(f"❓ Запрос: {test_query}")
    print("-" * 50)
    
    request_data = {
        "query": test_query
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Ответ получен:")
                    print(f"   Запрос: {result.get('query', '')}")
                    print(f"   Ответ: {result.get('response', '')}")
                    print(f"   Время: {result.get('timestamp', '')}")
                else:
                    print(f"❌ Ошибка HTTP: {response.status}")
                    text = await response.text()
                    print(f"   Ответ: {text}")
                    
    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def test_status():
    """Тест статуса API"""
    
    api_url = "http://localhost:8663/status"
    
    print(f"\n🚀 Проверяем статус API...")
    print(f"📡 URL: {api_url}")
    print("-" * 50)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Статус API:")
                    print(f"   Статус: {result.get('status', '')}")
                    print(f"   Агент инициализирован: {result.get('agent_initialized', '')}")
                    print(f"   Модель: {result.get('model', '')}")
                    print(f"   API URL: {result.get('api_url', '')}")
                    print(f"   MCP сервер: {result.get('mcp_server', '')}")
                else:
                    print(f"❌ Ошибка HTTP: {response.status}")
                    
    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def main():
    """Главная функция тестирования"""
    
    print("🧪 Тестирование FastAPI Streaming API с Qdrant Domains")
    print("=" * 60)
    
    # Проверяем статус
    #await test_status()
    
    # Тестируем streaming API
    #await test_streaming_api()
    
    # Тестируем простой chat
    await test_simple_chat()
    
    print("\n🏁 Тестирование завершено!")


if __name__ == "__main__":
    asyncio.run(main())
