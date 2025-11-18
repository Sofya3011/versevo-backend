import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

DATABASE_URL = f"sqlite:///./{settings.DB_PATH}"

engine = sa.create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)