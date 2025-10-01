#!/usr/bin/env python3
"""
JWT токены и аутентификация
"""

from datetime import datetime, timedelta
from typing import Optional
import jwt
import hashlib
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from auth_models import User, UserRole, get_db, UserSession
import secrets

# Настройки JWT
SECRET_KEY = "your-secret-key-change-in-production"  # В продакшене использовать переменную окружения
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 часа

security = HTTPBearer()

class AuthManager:
    """Менеджер аутентификации"""
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
        """Создание JWT токена"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        
        # Сохраняем токен в базе данных
        AuthManager._save_token_to_db(data.get("sub"), encoded_jwt, expire)
        
        return encoded_jwt
    
    @staticmethod
    def _save_token_to_db(user_id: int, token: str, expires_at: datetime):
        """Сохранение токена в базе данных"""
        db = next(get_db())
        try:
            # Создаем хеш из реального токена для безопасности
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            session = UserSession(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
                is_active=True
            )
            db.add(session)
            db.commit()
        except Exception as e:
            print(f"Ошибка сохранения токена: {e}")
            db.rollback()
        finally:
            db.close()
    
    @staticmethod
    def verify_token(token: str, db: Session) -> Optional[User]:
        """Проверка токена и получение пользователя"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                return None
            
            user = db.query(User).filter(User.username == username).first()
            if user is None or not user.is_active:
                return None
            
            # Проверяем, что сессия активна (токен не отозван)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            session = db.query(UserSession).filter(
                UserSession.token_hash == token_hash,
                UserSession.is_active == True,
                UserSession.expires_at > datetime.utcnow()
            ).first()
            
            if not session:
                return None
            
            # Обновляем время последнего входа
            user.last_login = datetime.utcnow()
            db.commit()
            
            return user
        except jwt.PyJWTError:
            return None
    
    @staticmethod
    def revoke_token(token: str):
        """Отзыв токена"""
        db = next(get_db())
        try:
            # Создаем хеш токена для поиска
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            # Находим сессию по хешу токена
            session = db.query(UserSession).filter(
                UserSession.token_hash == token_hash,
                UserSession.is_active == True
            ).first()
            
            if session:
                # Деактивируем сессию
                session.is_active = False
                db.commit()
                print(f"Токен успешно отозван для пользователя {session.user_id}")
            else:
                print("Токен не найден или уже отозван")
            
        except Exception as e:
            print(f"Ошибка отзыва токена: {e}")
            db.rollback()
        finally:
            db.close()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Получение текущего пользователя из токена"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        user = AuthManager.verify_token(token, db)
        if user is None:
            raise credentials_exception
        return user
    except Exception:
        raise credentials_exception

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Получение активного пользователя"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Требование роли администратора"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

def require_user_or_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Требование роли пользователя или администратора"""
    if current_user.role not in [UserRole.USER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user
