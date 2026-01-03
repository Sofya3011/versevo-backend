#!/bin/bash
echo "🚀 Starting Versevo Backend..."
echo "PORT: ${PORT}"

# Запускаем приложение
exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT} --access-log --log-level info
