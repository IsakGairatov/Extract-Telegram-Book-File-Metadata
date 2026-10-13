from telethon import TelegramClient


CHUNK_SIZE = 32 * 1024


async def download_part(
    message,
    offset,
    limit,
    client: TelegramClient
):
    """
    Получает только часть Telegram-файла

    offset — начало участка в байтах
    limit — количество байт
    """

    if limit <= 0:
        return b""

    data = bytearray()

    async for chunk in client.iter_download(
        message.document,
        offset=offset,
        limit=1,
        chunk_size=limit,
        request_size=limit
    ):
        data.extend(chunk)

        if len(data) >= limit:
            break

    return bytes(data[:limit])