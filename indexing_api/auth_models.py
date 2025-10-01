#!/usr/bin/env python3
"""
Модели SQLAlchemy для аутентификации пользователей
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
from enum import Enum
from passlib.context import CryptContext
import secrets

Base = declarative_base()

# Контекст для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserRole(str, Enum):
    """Роли пользователей"""
    ADMIN = "admin"
    USER = "user"

class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    
    def verify_password(self, password: str) -> bool:
        """Проверка пароля"""
        return pwd_context.verify(password, self.hashed_password)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Хеширование пароля"""
        # Ограничиваем пароль до 72 байт для bcrypt
        password_bytes = password.encode('utf-8')
        print(f"DEBUG: Password length: {len(password)} chars, {len(password_bytes)} bytes")
        if len(password_bytes) > 72:
            password = password[:72]
            print(f"DEBUG: Truncated password to: {len(password)} chars")
        return pwd_context.hash(password)
    
    def to_dict(self):
        """Преобразование в словарь (без пароля)"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }

class UserSession(Base):
    """Модель сессии пользователя для JWT токенов"""
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    token_hash = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

# Настройка базы данных
DATABASE_URL = "sqlite:///./qdrant_auth.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    """Создание таблиц в базе данных"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Получение сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_default_admin():
    """Создание администратора по умолчанию"""
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже администратор
        admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if admin:
            print("Администратор уже существует")
            return
        
        # Создаем администратора
        admin = User(
            username="admin",
            email="admin@qdrant.local",
            hashed_password=User.hash_password("admin123"),
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(admin)
        db.commit()
        print("✅ Администратор создан: username=admin, password=admin")
        
    except Exception as e:
        print(f"❌ Ошибка создания администратора: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Создаем таблицы и администратора
    create_tables()
    create_default_admin()
    print("База данных инициализирована")

