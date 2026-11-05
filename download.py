from telethon import TelegramClient


CHUNK_SIZE = 32 * 1024
ALIGNMENT = 4096

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

    file_size = message.document.size

    if offset >= file_size:
        return b""

    end = min(offset + limit, file_size)

    aligned_offset = (offset // ALIGNMENT) * ALIGNMENT
    skip = offset - aligned_offset
    required_size = end - aligned_offset



    data = bytearray()

    async for chunk in client.iter_download(
        message.document,
        offset=aligned_offset,
        limit=required_size,
        chunk_size=CHUNK_SIZE,
        request_size=CHUNK_SIZE
    ):
        data.extend(chunk)

        if len(data) >= required_size:
            break

    return bytes(data[skip:skip + (end - offset)])