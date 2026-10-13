import asyncio
import re

from telethon import TelegramClient

from config import API_ID, API_HASH, SESSION
from metadata.book import get_book_metadata

import metadata.fb2 as fb2_module
import metadata.epub as epub_module
import metadata.zip as zip_module
import metadata.pdf as pdf_module
import metadata.common as common_module

import download as download_module


# ============================================================
# СЧЁТЧИК СКАЧАННЫХ БАЙТ
# ============================================================

downloaded_bytes = 0

original_download_part = download_module.download_part


async def counted_download_part(*args, **kwargs):
    global downloaded_bytes

    data = await original_download_part(
        *args,
        **kwargs
    )

    if data:
        downloaded_bytes += len(data)

    return data


download_module.download_part = counted_download_part

fb2_module.download_part = counted_download_part
epub_module.download_part = counted_download_part
zip_module.download_part = counted_download_part
pdf_module.download_part = counted_download_part
common_module.download_part = counted_download_part


# ============================================================
# ПАРСИНГ ССЫЛКИ
# ============================================================

def parse_post_url(url):
    """
    Поддерживает:

        https://t.me/channel/123
        https://t.me/c/123456789/123
    """

    match = re.match(
        r"https?://t\.me/([^/]+)/(\d+)",
        url
    )

    if match:
        return match.group(1), int(match.group(2))

    match = re.match(
        r"https?://t\.me/c/(\d+)/(\d+)",
        url
    )

    if match:
        chat_id = int("-100" + match.group(1))
        return chat_id, int(match.group(2))

    raise ValueError(
        "Неверная ссылка на Telegram-пост"
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    global downloaded_bytes

    post_url = input(
        "Ссылка на Telegram-пост: "
    ).strip()

    chat, message_id = parse_post_url(
        post_url
    )

    async with TelegramClient(
        SESSION,
        API_ID,
        API_HASH
    ) as client:

        print()
        print("Получаем сообщение...")

        message = await client.get_messages(
            chat,
            ids=message_id
        )

        if not message:
            print("Сообщение не найдено.")
            return

        if not message.document:
            print("В посте нет файла.")
            return

        filename = message.file.name or ""

        file_size = message.document.size

        print()
        print("=" * 60)
        print("ФАЙЛ")
        print("=" * 60)

        print(f"Имя: {filename}")
        print(f"Размер: {file_size / 1024:.2f} КБ")
        print(f"Формат: {message.file.ext}")

        print()
        print("Получаем метаданные...")
        print()

        # ----------------------------------------------------
        # Метаданные
        # ----------------------------------------------------

        metadata = await get_book_metadata(
            client,
            chat,
            message_id
        )

        print("=" * 60)
        print("МЕТАДАННЫЕ")
        print("=" * 60)

        for key, value in metadata.items():
            print(
                f"{key}: {value}"
            )

        print()
        print("=" * 60)
        print("РАСХОД ТРАФИКА")
        print("=" * 60)

        print(
            f"Скачано: {downloaded_bytes} байт"
        )

        print(
            f"Скачано: {downloaded_bytes / 1024:.2f} КБ"
        )

        print(
            f"Скачано: "
            f"{downloaded_bytes / 1024 / 1024:.4f} МБ"
        )


if __name__ == "__main__":
    asyncio.run(main())