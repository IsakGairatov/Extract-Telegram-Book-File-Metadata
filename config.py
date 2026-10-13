import os

from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION = os.getenv("SESSION", "")
CHANNEL = os.getenv("CHANNEL", "")

FB2_CHUNK_SIZE = 32 * 1024
MAX_FB2_CHUNK_SIZE = 512 * 1024


# Конец ZIP, который читаем сначала
ZIP_TAIL_SIZE = 32 * 1024

# Максимум конца ZIP
MAX_ZIP_TAIL_SIZE = 256 * 1024

# Первый кусок сжатого FB2
ZIP_FB2_CHUNK_SIZE = 32 * 1024

# Максимум сжатого FB2, который разрешаем скачать
MAX_ZIP_FB2_CHUNK_SIZE = 512 * 1024
