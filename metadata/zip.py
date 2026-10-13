import re
import struct
import zlib

from config import ZIP_TAIL_SIZE, MAX_ZIP_TAIL_SIZE, ZIP_FB2_CHUNK_SIZE, MAX_ZIP_FB2_CHUNK_SIZE
from download import download_part
from metadata.common import get_zip_entries, parse_zip_entries, download_zip_entry
from metadata.epub import extract_epub_metadata
from metadata.fb2 import extract_fb2_metadata




async def get_zip_fb2_metadata(client, message, entry):
    """
    Читает FB2 внутри ZIP частями.

    Весь FB2 НЕ скачивает.
    """

    local_header_offset = (
        entry["local_header_offset"]
    )

    # --------------------------------------------------------
    # Читаем Local File Header
    # --------------------------------------------------------

    header = await download_part(
        message,
        local_header_offset,
        30,
        client
    )

    if len(header) < 30:
        return None

    if header[:4] != b"PK\x03\x04":
        return None

    filename_length = struct.unpack_from(
        "<H",
        header,
        26
    )[0]

    extra_length = struct.unpack_from(
        "<H",
        header,
        28
    )[0]

    data_offset = (
        local_header_offset
        + 30
        + filename_length
        + extra_length
    )

    compressed_size = (
        entry["compressed_size"]
    )

    # ========================================================
    # НЕСЖАТЫЙ FB2
    # ========================================================

    if entry["compression"] == 0:

        amount = min(
            compressed_size,
            ZIP_FB2_CHUNK_SIZE
        )

        data = await download_part(
            message,
            data_offset,
            amount,
            client
        )

        metadata = extract_fb2_metadata(
            data
        )

        return metadata

    # ========================================================
    # DEFLATE
    # ========================================================

    if entry["compression"] != 8:
        print(
            f"    Неподдерживаемое сжатие: "
            f"{entry['compression']}"
        )
        return None

    decompressor = zlib.decompressobj(
        -15
    )

    downloaded = 0
    chunk_size = ZIP_FB2_CHUNK_SIZE

    decoded_data = bytearray()

    while downloaded < compressed_size:

        if downloaded >= MAX_ZIP_FB2_CHUNK_SIZE:
            print(
                "    Достигнут лимит 512 КБ"
            )
            return None

        remaining = (
            compressed_size
            - downloaded
        )

        amount = min(
            chunk_size,
            remaining,
            MAX_ZIP_FB2_CHUNK_SIZE
            - downloaded
        )

        print(
            f"    FB2 внутри ZIP: "
            f"{downloaded / 1024:.0f} КБ"
        )

        compressed_chunk = await download_part(
            message,
            data_offset + downloaded,
            amount,
            client
        )

        if not compressed_chunk:
            return None

        downloaded += len(
            compressed_chunk
        )

        try:
            decompressed = (
                decompressor.decompress(
                    compressed_chunk
                )
            )
        except zlib.error as e:
            print(
                f"    Ошибка распаковки: {e}"
            )
            return None

        decoded_data.extend(
            decompressed
        )

        metadata = extract_fb2_metadata(
            bytes(decoded_data)
        )

        if metadata and (
                metadata["title"]
                or metadata["author"]
                or metadata["generated_at"]
        ):
            return metadata

        if len(compressed_chunk) < amount:
            return None

        chunk_size = min(
            chunk_size * 2,
            128 * 1024
        )

    return None

async def get_nested_epub_tail(
    client,
    message,
    epub_entry,
    amount
):
    """
    Получает только конец EPUB,
    находящегося внутри внешнего ZIP.

    Работает без скачивания всего EPUB,
    если EPUB внутри внешнего ZIP не сжат.
    """

    if epub_entry["compression"] != 0:

        print(
            "    EPUB внутри ZIP сжат — "
            "частичное чтение невозможно"
        )

        return None, None

    # --------------------------------------------------------
    # Local File Header внешнего EPUB
    # --------------------------------------------------------

    local_header_offset = (
        epub_entry["local_header_offset"]
    )

    header = await download_part(
        message,
        local_header_offset,
        30,
        client
    )

    if len(header) < 30:
        return None, None

    if header[:4] != b"PK\x03\x04":
        return None, None

    filename_length = struct.unpack_from(
        "<H",
        header,
        26
    )[0]

    extra_length = struct.unpack_from(
        "<H",
        header,
        28
    )[0]

    epub_data_offset = (
        local_header_offset
        + 30
        + filename_length
        + extra_length
    )

    epub_size = epub_entry[
        "uncompressed_size"
    ]

    amount = min(
        amount,
        epub_size
    )

    # Смещение внутри EPUB
    epub_offset = (
        epub_size - amount
    )

    # Реальное смещение в Telegram-файле
    telegram_offset = (
        epub_data_offset
        + epub_offset
    )

    data = await download_part(
        message,
        telegram_offset,
        amount,
        client
    )

    return data, epub_offset


async def get_nested_epub_entries(
    client,
    message,
    epub_entry
):
    """
    Находит Central Directory вложенного EPUB,
    скачивая только его конец.
    """

    if epub_entry["compression"] != 0:
        return None

    epub_size = epub_entry[
        "uncompressed_size"
    ]

    amount = min(
        epub_size,
        ZIP_TAIL_SIZE
    )

    while True:

        print(
            f"    Читаем конец EPUB: "
            f"{amount / 1024:.0f} КБ"
        )

        tail, tail_offset = (
            await get_nested_epub_tail(
                client,
                message,
                epub_entry,
                amount
            )
        )

        if tail is None:
            return None

        entries = parse_zip_entries(
            tail,
            tail_offset
        )

        if entries is not None:
            return entries

        if amount >= epub_size:
            return None

        if amount >= MAX_ZIP_TAIL_SIZE:
            return None

        amount = min(
            amount * 2,
            MAX_ZIP_TAIL_SIZE,
            epub_size
        )


async def download_nested_epub_entry(
    client,
    message,
    epub_entry,
    inner_entry
):
    """
    Скачивает только один файл из EPUB.

    EPUB находится внутри внешнего ZIP.
    """

    if epub_entry["compression"] != 0:
        return None

    # --------------------------------------------------------
    # Local Header внешнего EPUB
    # --------------------------------------------------------

    outer_offset = (
        epub_entry["local_header_offset"]
    )

    outer_header = await download_part(
        message,
        outer_offset,
        30,
        client
    )

    if len(outer_header) < 30:
        return None

    if outer_header[:4] != b"PK\x03\x04":
        return None

    outer_filename_length = struct.unpack_from(
        "<H",
        outer_header,
        26
    )[0]

    outer_extra_length = struct.unpack_from(
        "<H",
        outer_header,
        28
    )[0]

    epub_data_offset = (
        outer_offset
        + 30
        + outer_filename_length
        + outer_extra_length
    )

    # --------------------------------------------------------
    # Local Header файла внутри EPUB
    # --------------------------------------------------------

    inner_offset = (
        inner_entry["local_header_offset"]
    )

    inner_header = await download_part(
        message,
        epub_data_offset + inner_offset,
        30,
        client
    )

    if len(inner_header) < 30:
        return None

    if inner_header[:4] != b"PK\x03\x04":
        return None

    inner_filename_length = struct.unpack_from(
        "<H",
        inner_header,
        26
    )[0]

    inner_extra_length = struct.unpack_from(
        "<H",
        inner_header,
        28
    )[0]

    inner_data_offset = (
        epub_data_offset
        + inner_offset
        + 30
        + inner_filename_length
        + inner_extra_length
    )

    compressed_size = (
        inner_entry["compressed_size"]
    )

    # --------------------------------------------------------
    # Скачиваем только OPF
    # --------------------------------------------------------

    data = await download_part(
        message,
        inner_data_offset,
        compressed_size,
        client
    )

    if inner_entry["compression"] == 0:
        return data

    if inner_entry["compression"] == 8:

        try:

            return zlib.decompress(
                data,
                -15
            )

        except zlib.error as e:

            print(
                f"    Ошибка распаковки OPF: {e}"
            )

            return None

    print(
        f"    Неподдерживаемое сжатие OPF: "
        f"{inner_entry['compression']}"
    )

    return None

async def get_zip_folder_epub_metadata(
    client,
    message,
    entries,
    epub_prefix
):
    """
    Получает метаданные EPUB,
    который находится в ZIP как папка.

    Например:

        book.epub/
            mimetype
            META-INF/container.xml
            OEBPS/content.opf
    """

    prefix = epub_prefix.rstrip("/") + "/"

    # --------------------------------------------------------
    # Ищем container.xml
    # --------------------------------------------------------

    container_entry = None

    for entry in entries:

        filename = entry["filename"]

        if filename.lower() == (
            prefix + "meta-inf/container.xml"
        ).lower():
            container_entry = entry
            break

    if not container_entry:
        print(
            f"    container.xml не найден: {prefix}"
        )
        return None

    # --------------------------------------------------------
    # Скачиваем container.xml
    # --------------------------------------------------------

    data = await download_zip_entry(
        client,
        message,
        container_entry
    )

    if not data:
        return None

    text = data.decode(
        "utf-8",
        errors="replace"
    )

    # --------------------------------------------------------
    # Ищем путь к OPF
    # --------------------------------------------------------

    match = re.search(
        r"<rootfile\b[^>]*full-path\s*=\s*[\"']([^\"']+)",
        text,
        re.IGNORECASE
    )

    if not match:
        print(
            "    OPF не найден в container.xml"
        )
        return None

    opf_path = match.group(1)

    opf_filename = (
        prefix + opf_path
    ).replace(
        "//",
        "/"
    )

    # --------------------------------------------------------
    # Ищем OPF во внешнем ZIP
    # --------------------------------------------------------

    opf_entry = None

    for entry in entries:

        if entry["filename"].lower() == (
            opf_filename
        ).lower():
            opf_entry = entry
            break

    if not opf_entry:
        print(
            f"    OPF отсутствует в ZIP: "
            f"{opf_filename}"
        )
        return None

    print(
        f"    Найден OPF: "
        f"{opf_entry['filename']}"
    )

    # --------------------------------------------------------
    # Скачиваем только OPF
    # --------------------------------------------------------

    opf_data = await download_zip_entry(
        client,
        message,
        opf_entry
    )

    if not opf_data:
        return None

    metadata = extract_epub_metadata(
        opf_data
    )

    if (
        metadata["title"]
        or metadata["author"]
        or metadata["generated_at"]
    ):
        return metadata

    return None

async def get_zip_epub_metadata(
    client,
    message,
    epub_entry
):
    """
    Получает title из EPUB внутри ZIP,
    не скачивая весь EPUB.

    Схема:

        внешний ZIP
            ↓
        *.epub
            ↓
        конец EPUB
            ↓
        Central Directory
            ↓
        *.opf
            ↓
        title
    """

    print(
        f"    Найден EPUB: "
        f"{epub_entry['filename']}"
    )

    # --------------------------------------------------------
    # Central Directory внутреннего EPUB
    # --------------------------------------------------------

    entries = await get_nested_epub_entries(
        client,
        message,
        epub_entry
    )

    if not entries:

        print(
            "    Не удалось прочитать EPUB"
        )

        return None

    print(
        f"    Файлов внутри EPUB: "
        f"{len(entries)}"
    )

    # --------------------------------------------------------
    # Ищем OPF
    # --------------------------------------------------------

    for entry in entries:

        filename = entry[
            "filename"
        ]

        if not filename.lower().endswith(
            ".opf"
        ):
            continue

        print(
            f"    Найден OPF: {filename}"
        )

        opf_data = (
            await download_nested_epub_entry(
                client,
                message,
                epub_entry,
                entry
            )
        )

        if not opf_data:
            continue

        metadata = extract_epub_metadata(
            opf_data
        )

        if (
                metadata["title"]
                or metadata["author"]
                or metadata["generated_at"]
        ):
            return metadata

    print(
        "    OPF не найден"
    )

    return None

# ============================================================
# ПОЛУЧИТЬ Metadata ИЗ ZIP
# ============================================================


async def get_zip_metadata(
    client,
    message
):
    """
    Получает метаданные книги из ZIP.

    Ищет:
        1. FB2
        2. EPUB

    Сам ZIP целиком не скачивает.
    """

    entries = await get_zip_entries(
        client,
        message
    )

    if not entries:
        return {
            "title": None,
            "author": None,
            "generated_at": None
        }

    print(
        f"    Файлов в ZIP: {len(entries)}"
    )

    # ========================================================
    # FB2
    # ========================================================

    for entry in entries:

        filename = entry[
            "filename"
        ]

        if not filename.lower().endswith(
            ".fb2"
        ):
            continue

        print(
            f"    Найден FB2: {filename}"
        )

        metadata = await get_zip_fb2_metadata(
            client,
            message,
            entry
        )

        if metadata:
            return metadata

    # ========================================================
    # EPUB
    # ========================================================

    # --------------------------------------------------------
    # Вариант 1: EPUB является отдельным .epub-файлом
    # --------------------------------------------------------

    for entry in entries:

        filename = entry["filename"]

        if not filename.lower().endswith(
                ".epub"
        ):
            continue

        metadata = await get_zip_epub_metadata(
            client,
            message,
            entry
        )

        if metadata:
            return metadata

    # --------------------------------------------------------
    # Вариант 2: EPUB является папкой *.epub/
    # --------------------------------------------------------

    epub_prefixes = set()

    for entry in entries:

        filename = entry["filename"]

        parts = filename.split("/")

        if len(parts) < 2:
            continue

        first_part = parts[0]

        if first_part.lower().endswith(
                ".epub"
        ):
            epub_prefixes.add(
                first_part
            )

    for epub_prefix in epub_prefixes:

        print(
            f"    Найдена папка EPUB: "
            f"{epub_prefix}/"
        )

        metadata = await get_zip_folder_epub_metadata(
            client,
            message,
            entries,
            epub_prefix
        )

        if metadata:
            return metadata

    # ========================================================
    # Ничего не нашли
    # ========================================================

    return {
        "title": None,
        "author": None,
        "generated_at": None
    }