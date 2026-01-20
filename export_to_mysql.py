#!/usr/bin/env python3
"""
Скрипт для экспорта схемы PostgreSQL в MySQL
"""

from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.schema import CreateTable
import os
from dotenv import load_dotenv

load_dotenv()

def export_postgres_schema():
    """Экспорт схемы PostgreSQL"""
    
    # Подключаемся к PostgreSQL (Railway)
    DATABASE_URL = os.getenv("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    if not DATABASE_URL:
        DATABASE_URL = "postgresql://postgres:password@localhost/versevo"
    
    pg_engine = create_engine(DATABASE_URL)
    
    try:
        # Получаем метаданные
        metadata = MetaData()
        metadata.reflect(bind=pg_engine)
        
        # Создаем MySQL DDL
        mysql_ddl = []
        
        for table_name, table in metadata.tables.items():
            # Генерируем CREATE TABLE для MySQL
            create_stmt = CreateTable(table)
            
            # Конвертируем PostgreSQL типы в MySQL
            ddl = str(create_stmt.compile(pg_engine))
            
            # Заменяем PostgreSQL специфичные типы
            ddl = ddl.replace('SERIAL', 'INT AUTO_INCREMENT')
            ddl = ddl.replace('TIMESTAMP WITHOUT TIME ZONE', 'TIMESTAMP')
            ddl = ddl.replace('VARCHAR', 'VARCHAR')
            ddl = ddl.replace('TEXT', 'LONGTEXT')
            ddl = ddl.replace('BOOLEAN', 'TINYINT(1)')
            ddl = ddl.replace('INTEGER', 'INT')
            ddl = ddl.replace('BYTEA', 'LONGBLOB')
            
            # Добавляем ENGINE и CHARSET
            ddl = ddl.rstrip() + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
            
            mysql_ddl.append(ddl)
            
            # Получаем индексы
            for index in table.indexes:
                index_ddl = str(index.compile(pg_engine))
                mysql_ddl.append(index_ddl + ";")
        
        # Сохраняем в файл
        with open("mysql_schema.sql", "w", encoding="utf-8") as f:
            f.write("-- MySQL Schema for Versevo\n")
            f.write("-- Generated from PostgreSQL schema\n\n")
            f.write("CREATE DATABASE IF NOT EXISTS versevo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n")
            f.write("USE versevo;\n\n")
            
            for ddl in mysql_ddl:
                f.write(ddl + "\n\n")
        
        print("✅ MySQL схема сохранена в mysql_schema.sql")
        
        # Создаем файл с тестовыми данными
        create_sample_data()
        
    except Exception as e:
        print(f"❌ Ошибка экспорта схемы: {e}")

def create_sample_data():
    """Создание тестовых данных для демонстрации"""
    
    sample_data = """
-- Sample Data for Reports
INSERT INTO users (email, username, hashed_password, created_at, last_login) VALUES
('admin@example.com', 'admin', '$2b$12$...hash...', NOW() - INTERVAL 30 DAY, NOW()),
('user1@example.com', 'user1', '$2b$12$...hash...', NOW() - INTERVAL 15 DAY, NOW() - INTERVAL 2 DAY),
('user2@example.com', 'user2', '$2b$12$...hash...', NOW() - INTERVAL 7 DAY, NOW() - INTERVAL 1 DAY);

INSERT INTO documents (user_id, filename, content, language, file_type, word_count, char_count, created_at) VALUES
(1, 'pride_and_prejudice.pdf', 'It is a truth universally acknowledged...', 'en', 'pdf', 125000, 650000, NOW() - INTERVAL 20 DAY),
(2, 'war_and_peace.txt', 'Well, Prince, so Genoa and Lucca...', 'ru', 'txt', 560000, 3000000, NOW() - INTERVAL 10 DAY),
(3, 'test_document.docx', 'Test document content...', 'en', 'docx', 1500, 8500, NOW() - INTERVAL 5 DAY);

INSERT INTO document_analysis (document_id, analysis_type, summary, themes, sentiment, ai_analysis, ai_provider, created_at) VALUES
(1, 'full', 'A novel of manners...', 'marriage, class, prejudice', 'Positive', true, 'gemini', NOW() - INTERVAL 5 DAY),
(2, 'standard', 'Epic historical novel...', 'war, peace, history', 'Neutral', true, 'huggingface', NOW() - INTERVAL 3 DAY),
(3, 'quick', 'Simple test document...', 'test, example', 'Neutral', false, NULL, NOW() - INTERVAL 1 DAY);

INSERT INTO favorite_quotes (document_id, quote, created_at) VALUES
(1, 'It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.', NOW() - INTERVAL 4 DAY),
(2, 'All happy families are alike; each unhappy family is unhappy in its own way.', NOW() - INTERVAL 2 DAY);

INSERT INTO document_notes (document_id, user_id, text, created_at) VALUES
(1, 1, 'Interesting analysis of class dynamics', NOW() - INTERVAL 3 DAY),
(2, 2, 'Historical context is important here', NOW() - INTERVAL 1 DAY);

-- Создание таблицы для переводов если её нет
CREATE TABLE IF NOT EXISTS translation_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    original_text_hash VARCHAR(64),
    original_text LONGTEXT,
    translated_text LONGTEXT,
    source_language VARCHAR(10),
    target_language VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO translation_cache (original_text_hash, original_text, translated_text, source_language, target_language) VALUES
('abc123', 'Hello world', 'Привет мир', 'en', 'ru', NOW() - INTERVAL 2 DAY),
('def456', 'Good morning', 'Доброе утро', 'en', 'ru', NOW() - INTERVAL 1 DAY);
"""
    
    with open("sample_data.sql", "w", encoding="utf-8") as f:
        f.write(sample_data)
    
    print("✅ Тестовые данные сохранены в sample_data.sql")

if __name__ == "__main__":
    export_postgres_schema()
