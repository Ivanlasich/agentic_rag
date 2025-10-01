import os
import asyncio
import aiofiles
import re
from typing import List, Optional
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileParser:
    """Класс для парсинга различных форматов файлов в текст"""
    
    def __init__(self):
        self.supported_extensions = {
            '.txt': self._parse_txt,
            '.md': self._parse_txt,
            '.rst': self._parse_txt,
            '.pdf': self._parse_pdf,
            '.xlsx': self._parse_xlsx,
            '.xls': self._parse_xlsx,
            '.docx': self._parse_docx,
            '.doc': self._parse_doc,
            '.csv': self._parse_csv
        }
    
    def _clean_text(self, text: str) -> str:
        """Очистка текста от лишних пробелов"""
        if not text:
            return text
        
        # Заменяем множественные пробелы на одинарные
        text = re.sub(r' +', ' ', text)
        
        # Заменяем множественные переносы строк на максимум 2
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Убираем пробелы в начале и конце строк
        lines = text.split('\n')
        cleaned_lines = [line.rstrip() for line in lines]
        text = '\n'.join(cleaned_lines)
        
        # Убираем пробелы в начале и конце всего текста
        return text.strip()
    
    async def parse_file(self, file_path: str) -> Optional[str]:
        """
        Парсит файл любого поддерживаемого формата в текст
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Текст файла или None в случае ошибки
        """
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext not in self.supported_extensions:
                logger.warning(f"Неподдерживаемый формат файла: {file_ext}")
                return None
            
            parser_func = self.supported_extensions[file_ext]
            return await parser_func(file_path)
            
        except Exception as e:
            logger.error(f"Ошибка парсинга файла {file_path}: {e}")
            return None
    
    async def parse_file_to_chunks(self, file_path: str, chunk_size: int = 1000) -> List[str]:
        """
        Парсит файл и разбивает на чанки для индексации
        
        Args:
            file_path: Путь к файлу
            chunk_size: Размер чанка в символах
            
        Returns:
            Список текстовых чанков
        """
        text = await self.parse_file(file_path)
        if not text:
            return []
        
        return self._split_text_to_chunks(text, chunk_size)
    
    def _split_text_to_chunks(self, text: str, chunk_size: int) -> List[str]:
        """Разбивает текст на чанки"""
        chunks = []
        words = text.split()
        current_chunk = []
        current_size = 0
        
        for word in words:
            word_size = len(word) + 1  # +1 для пробела
            
            if current_size + word_size > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_size = word_size
            else:
                current_chunk.append(word)
                current_size += word_size
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks
    
    async def _parse_txt(self, file_path: str) -> str:
        """Парсинг текстовых файлов (.txt, .md, .rst)"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                return await f.read()
        except UnicodeDecodeError:
            # Пробуем другие кодировки
            try:
                async with aiofiles.open(file_path, 'r', encoding='cp1251') as f:
                    return await f.read()
            except UnicodeDecodeError:
                async with aiofiles.open(file_path, 'r', encoding='latin-1') as f:
                    return await f.read()
    
    async def _parse_pdf(self, file_path: str) -> str:
        """Парсинг PDF файлов"""
        try:
            import PyPDF2
        except ImportError:
            logger.error("PyPDF2 не установлен. Установите: pip install PyPDF2")
            return ""
        
        try:
            text = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except Exception as e:
            logger.error(f"Ошибка парсинга PDF {file_path}: {e}")
            return ""
    
    async def _parse_xlsx(self, file_path: str) -> str:
        """Парсинг Excel файлов (.xlsx, .xls)"""
        try:
            import pandas as pd
            import io
            
            # Используем StringIO для записи в строку
            output = io.StringIO()
            
            # Читаем Excel файл и сразу записываем в StringIO
            pd.read_excel(file_path).to_string(output, index=False)
            
            # Очищаем текст от лишних пробелов
            text = output.getvalue()
            text = self._clean_text(text)
            return text
            
        except ImportError:
            logger.error("pandas не установлен. Установите: pip install pandas openpyxl")
            return ""
        except Exception as e:
            logger.error(f"Ошибка парсинга Excel {file_path}: {e}")
            return ""
    
    async def _parse_docx(self, file_path: str) -> str:
        """Парсинг DOCX файлов"""
        try:
            from docx import Document
        except ImportError:
            logger.error("python-docx не установлен. Установите: pip install python-docx")
            return ""
        
        try:
            doc = Document(file_path)
            text_parts = []
            
            for paragraph in doc.paragraphs:
                text_parts.append(paragraph.text)
            
            return "\n".join(text_parts)
        except Exception as e:
            logger.error(f"Ошибка парсинга DOCX {file_path}: {e}")
            return ""
    
    async def _parse_doc(self, file_path: str) -> str:
        """Парсинг DOC файлов (старый формат Word)"""
        try:
            import subprocess
            import tempfile
            
            # Конвертируем DOC в TXT через antiword (если доступен)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                result = subprocess.run(['antiword', file_path], 
                                     capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return result.stdout
                else:
                    logger.warning(f"antiword не смог обработать файл {file_path}")
                    return ""
            except (subprocess.TimeoutExpired, FileNotFoundError):
                logger.warning("antiword не найден или превышено время ожидания")
                return ""
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    
        except Exception as e:
            logger.error(f"Ошибка парсинга DOC {file_path}: {e}")
            return ""
    
    async def _parse_csv(self, file_path: str) -> str:
        """Парсинг CSV файлов"""
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas не установлен. Установите: pip install pandas")
            return ""
        
        try:
            df = pd.read_csv(file_path)
            return df.to_string(index=False)
        except Exception as e:
            logger.error(f"Ошибка парсинга CSV {file_path}: {e}")
            return ""
    
    async def convert_and_save_as_txt(self, file_path: str, output_path: str) -> bool:
        """
        Конвертирует файл в текст и сохраняет как .txt файл
        
        Args:
            file_path: Путь к исходному файлу
            output_path: Путь для сохранения текстового файла
            
        Returns:
            True если конвертация успешна, False иначе
        """
        try:
            text = await self.parse_file(file_path)
            if not text:
                return False
            
            # Создаем директорию если не существует
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
                await f.write(text)
            
            logger.info(f"Файл {file_path} успешно конвертирован в {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка конвертации файла {file_path}: {e}")
            return False

# Глобальный экземпляр парсера
file_parser = FileParser()

