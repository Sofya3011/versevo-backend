import os
import sys

print("=== Checking environment ===")
print(f"Current directory: {os.getcwd()}")
print(f"Python path: {sys.path}")

# Проверяем файлы
print("\n=== Directory structure ===")
for root, dirs, files in os.walk("."):
    level = root.replace(".", "").count(os.sep)
    indent = " " * 2 * level
    print(f"{indent}{os.path.basename(root)}/")
    subindent = " " * 2 * (level + 1)
    for file in files[:5]:  # Показываем первые 5 файлов
        print(f"{subindent}{file}")

print("\n=== Trying to import ===")
try:
    from services.main import app
    print("✅ Successfully imported app from services.main")
    
    # Проверяем endpoints
    import asyncio
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    response = client.get("/api/flutter/health")
    print(f"✅ Health check response: {response.status_code}")
    print(f"✅ Health check data: {response.json()}")
    
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
