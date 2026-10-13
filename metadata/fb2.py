import re
from html import unescape

from config import FB2_CHUNK_SIZE, MAX_FB2_CHUNK_SIZE
from download import download_part
from metadata.common import clean_text, decode_fb2
from metadata.common import extract_tag_value


def extract_fb2_author(
    text
):
    """
    Извлекает автора FB2.

    Поддерживает:

        first-name
        middle-name
        last-name
        nickname
    """

    author_match = re.search(
        r"<(?:[\w.-]+:)?author\b[^>]*>"
        r"(.*?)"
        r"</(?:[\w.-]+:)?author>",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if not author_match:
        return None

    author_block = author_match.group(1)

    # --------------------------------------------------------
    # Сначала пытаемся получить имя / фамилию
    # --------------------------------------------------------

    first_name = extract_tag_value(
        author_block,
        "first-name"
    )

    middle_name = extract_tag_value(
        author_block,
        "middle-name"
    )

    last_name = extract_tag_value(
        author_block,
        "last-name"
    )

    parts = []

    if first_name:
        parts.append(
            first_name
        )

    if middle_name:
        parts.append(
            middle_name
        )

    if last_name:
        parts.append(
            last_name
        )

    if parts:

        return " ".join(
            parts
        )

    # --------------------------------------------------------
    # Если имени нет — используем nickname
    # --------------------------------------------------------

    nickname = extract_tag_value(
        author_block,
        "nickname"
    )

    if nickname:
        return nickname

    return None


def extract_fb2_date(
    text
):
    """
    Получает дату создания FB2.

    Ищет:

        <document-info>
            <date>...</date>
        </document-info>

    Приоритет:
        value="..."
        затем содержимое <date>
    """

    document_info_match = re.search(
        r"<(?:[\w.-]+:)?document-info\b[^>]*>"
        r"(.*?)"
        r"</(?:[\w.-]+:)?document-info>",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if not document_info_match:
        return None

    document_info = document_info_match.group(1)

    # --------------------------------------------------------
    # <date value="2024-05-17">
    # --------------------------------------------------------

    date_match = re.search(
        r"<(?:[\w.-]+:)?date\b[^>]*"
        r"\bvalue\s*=\s*[\"']([^\"']+)[\"']"
        r"[^>]*>",
        document_info,
        re.IGNORECASE
    )

    if date_match:

        return clean_text(
            date_match.group(1)
        )

    # --------------------------------------------------------
    # <date>2024-05-17</date>
    # --------------------------------------------------------

    date_match = re.search(
        r"<(?:[\w.-]+:)?date\b[^>]*>"
        r"(.*?)"
        r"</(?:[\w.-]+:)?date>",
        document_info,
        re.IGNORECASE | re.DOTALL
    )

    if date_match:

        return clean_text(
            date_match.group(1)
        )

    return None


def extract_fb2_metadata(
    data
):
    """
    Извлекает:

        title
        author
        generated_at

    из FB2.
    """

    text = decode_fb2(
        data
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = extract_tag_value(
        text,
        "book-title"
    )

    # --------------------------------------------------------
    # AUTHOR
    # --------------------------------------------------------

    author = extract_fb2_author(
        text
    )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    generated_at = extract_fb2_date(
        text
    )

    return {
        "title": title,
        "author": author,
        "generated_at": generated_at
    }

#v2

async def get_fb2_metadata(
    client,
    message
):
    """
    Получает метаданные FB2.

    Скачивает файл постепенно, добавляя только недостающую часть.
    """

    file_size = message.document.size

    amount = min(
        file_size,
        FB2_CHUNK_SIZE
    )

    downloaded = bytearray()

    while True:

        current_size = len(downloaded)

        needed = amount - current_size

        if needed > 0:

            data = await download_part(
                message,
                current_size,
                needed,
                client
            )

            downloaded.extend(data)

        metadata = extract_fb2_metadata(
            bytes(downloaded)
        )

        if (
            metadata["title"]
            and metadata["author"]
            and metadata["generated_at"]
        ):
            return metadata

        if len(downloaded) >= file_size:
            return metadata

        if len(downloaded) >= MAX_FB2_CHUNK_SIZE:
            return metadata

        amount = min(
            amount + FB2_CHUNK_SIZE,
            MAX_FB2_CHUNK_SIZE,
            file_size
        )

def extract_fb2_title(data):
    """
    Ищет <book-title> в переданном куске FB2
    и автоматически определяет кодировку.
    """

    # Определяем кодировку из XML-заголовка
    encoding_match = re.search(
        rb'<\?xml[^>]+encoding=["\']([^"\']+)["\']',
        data[:1000],
        re.IGNORECASE
    )

    if encoding_match:
        encoding = encoding_match.group(1).decode(
            "ascii",
            errors="ignore"
        )
    else:
        encoding = "utf-8"

    # Ищем book-title прямо в байтах
    match = re.search(
        rb"<book-title[^>]*>(.*?)</book-title>",
        data,
        re.IGNORECASE | re.DOTALL
    )

    if not match:
        return None

    title = match.group(1)

    # Убираем XML-теги
    title = re.sub(
        rb"<[^>]+>",
        b"",
        title
    )

    # Декодируем найденный текст
    try:
        title = title.decode(
            encoding,
            errors="replace"
        )
    except LookupError:
        title = title.decode(
            "utf-8",
            errors="replace"
        )

    # XML-сущности
    title = unescape(title)

    # Убираем лишние пробелы и переносы
    title = " ".join(
        title.split()
    )

    return title.strip() or None