import logging
import sys

# Настройка логирования БЕЗ Uvicorn
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Отключаем стандартные логи Uvicorn
import uvicorn.config
uvicorn.config.LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s - %(levelname)s - %(message)s"

app = FastAPI()

@app.on_event("startup")
async def startup():
    logger.info("🚀 Versevo Backend STARTED")
    logger.info(f"Port: {os.getenv('PORT', 8080)}")
