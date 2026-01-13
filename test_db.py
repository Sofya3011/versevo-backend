# test_db.py
import psycopg2

# Ваша строка подключения
conn_string = "postgresql://postgres:BQIGEvhzTcTvyCSYqzLtcMOMjzlVjUQg@shinkansen.proxy.rlwy.net:48342/railway"

try:
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    
    # Проверяем версию PostgreSQL
    cursor.execute("SELECT version()")
    version = cursor.fetchone()
    print(f"✅ Подключено к PostgreSQL: {version[0]}")
    
    # Проверяем таблицы
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    tables = cursor.fetchall()
    print(f"📊 Таблицы в базе: {[t[0] for t in tables]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
