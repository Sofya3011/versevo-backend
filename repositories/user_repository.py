# repositories/user_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import User
import bcrypt

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_user(self, email: str, username: str, password: str) -> User:
        """Создание нового пользователя"""
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user = User(
            email=email,
            username=username,
            password_hash=password_hash
        )
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user
    
    async def get_user_by_email(self, email: str):
        """Поиск пользователя по email"""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_id(self, user_id: int):
        """Поиск пользователя по ID"""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Проверка пароля"""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
