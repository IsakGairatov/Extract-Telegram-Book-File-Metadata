# ============================================================
# PDF
# ============================================================
import re
from pathlib import Path

from download import download_part
from metadata.common import clean_text


PDF_METADATA_CHUNK_SIZE = 32 * 1024

def extract_xmp_value(
    xml,
    names
):
    """
    Ищет значение XML/XMP-поля.

    names — список возможных названий поля.
    """

    if not xml:
        return None

    for name in names:

        # ----------------------------------------------------
        # <dc:title>...</dc:title>
        # <pdf:Author>...</pdf:Author>
        # ----------------------------------------------------

        match = re.search(
            rf"<(?:[\w.-]+:)?{re.escape(name)}\b[^>]*>"
            rf"(.*?)"
            rf"</(?:[\w.-]+:)?{re.escape(name)}>",
            xml,
            re.IGNORECASE | re.DOTALL
        )

        if match:

            value = clean_text(
                match.group(1)
            )

            if value:
                return value

        # ----------------------------------------------------
        # <dc:title>...rdf:li...
        # ----------------------------------------------------

        match = re.search(
            rf"<(?:[\w.-]+:)?{re.escape(name)}\b[^>]*>"
            rf".*?<rdf:li[^>]*>"
            rf"(.*?)"
            rf"</rdf:li>"
            rf".*?</(?:[\w.-]+:)?{re.escape(name)}>",
            xml,
            re.IGNORECASE | re.DOTALL
        )

        if match:

            value = clean_text(
                match.group(1)
            )

            if value:
                return value

    return None


def extract_pdf_xmp_metadata(
    xml
):
    """
    Извлекает метаданные из XMP/XML PDF.

    Ищет:

        title
        author
        published
        date
    """

    if not xml:
        return {
            "title": None,
            "author": None,
            "published": None,
            "date": None
        }

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = extract_xmp_value(
        xml,
        [
            "title",
            "Title"
        ]
    )

    # --------------------------------------------------------
    # AUTHOR
    # --------------------------------------------------------

    author = extract_xmp_value(
        xml,
        [
            "creator",
            "Creator",
            "author",
            "Author"
        ]
    )

    # --------------------------------------------------------
    # PUBLISHED
    # --------------------------------------------------------

    published = extract_xmp_value(
        xml,
        [
            "published",
            "Published",
            "pubdate",
            "PubDate",
            "pubDate"
        ]
    )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    date = extract_xmp_value(
        xml,
        [
            "date",
            "Date",
            "CreateDate",
            "ModifyDate",
            "MetadataDate"
        ]
    )

    return {
        "title": title,
        "author": author,
        "published": published,
        "date": date
    }

def decode_pdf_literal_string(raw):
    """
    Разбирает содержимое PDF-строки в круглых скобках.
    Обрабатывает восьмеричные escape-последовательности,
    экранированные скобки, обратные слеши и переносы строк.
    """
    result = bytearray()
    i = 0

    while i < len(raw):
        byte = raw[i]

        if byte != 0x5C:  # обратный слеш
            result.append(byte)
            i += 1
            continue

        i += 1

        if i >= len(raw):
            break

        byte = raw[i]

        # Перенос строки после обратного слеша игнорируется
        if byte == 0x0D:
            i += 1
            if i < len(raw) and raw[i] == 0x0A:
                i += 1
            continue

        if byte == 0x0A:
            i += 1
            continue

        # Восьмеричная последовательность: \ddd
        if 0x30 <= byte <= 0x37:
            digits = bytearray()

            for _ in range(3):
                if (
                    i < len(raw)
                    and 0x30 <= raw[i] <= 0x37
                ):
                    digits.append(raw[i])
                    i += 1
                else:
                    break

            result.append(int(digits, 8) & 0xFF)
            continue

        # Стандартные PDF escape-последовательности
        escapes = {
            ord("n"): 0x0A,
            ord("r"): 0x0D,
            ord("t"): 0x09,
            ord("b"): 0x08,
            ord("f"): 0x0C,
            ord("("): 0x28,
            ord(")"): 0x29,
            ord("\\"): 0x5C,
        }

        result.append(escapes.get(byte, byte))
        i += 1

    return decode_pdf_text(bytes(result))


def decode_pdf_text(raw):
    """
    Декодирует байты PDF-строки.
    """
    if not raw:
        return ""

    # UTF-16BE с BOM
    if raw.startswith(b"\xfe\xff"):
        try:
            return raw[2:].decode("utf-16-be")
        except UnicodeDecodeError:
            return ""

    # UTF-16LE с BOM
    if raw.startswith(b"\xff\xfe"):
        try:
            return raw[2:].decode("utf-16-le")
        except UnicodeDecodeError:
            return ""

    # PDFDocEncoding — стандартная кодировка PDF-строк
    try:
        from pypdf.generic import decode_pdfdocencoding
        return decode_pdfdocencoding(raw)
    except (ImportError, UnicodeDecodeError, ValueError):
        pass

    # Резерв для нестандартных PDF
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")



def extract_pdf_info_value(
    data,
    names
):
    """
    Ищет стандартные PDF Info-поля
    непосредственно в байтах PDF.

    Например:

        /Title (Название книги)
        /Author (Автор)

    """

    if not data:
        return None

    for name in names:

        # ----------------------------------------------------
        # Обычная PDF-строка:
        #
        # /Title (Название книги)
        # ----------------------------------------------------

        match = re.search(
            rb"/" + re.escape(name.encode()) +
            rb"\s*\((.*?)\)",
            data,
            re.DOTALL
        )

        if match:

            value = decode_pdf_literal_string(
                match.group(1)
            )

            value = clean_text(
                value
            )

            if value:
                return value

        # ----------------------------------------------------
        # PDF hexadecimal string:
        #
        # /Title <...>
        # ----------------------------------------------------

        match = re.search(
            rb"/" + re.escape(name.encode()) +
            rb"\s*<([0-9A-Fa-f\s]+)>",
            data
        )

        if match:

            hex_data = re.sub(
                rb"\s+",
                b"",
                match.group(1)
            )

            try:

                value = bytes.fromhex(
                    hex_data.decode("ascii")
                )

                value = decode_pdf_text(value)

                value = clean_text(
                    value
                )

                if value:
                    return value


            except (UnicodeDecodeError, ValueError):
                pass

    return None

def extract_pdf_metadata_from_bytes(
    data
):
    """
    Ищет метаданные PDF только в переданном
    участке файла.

    Полный PDF не требуется.
    """

    if not data:
        return {
            "title": None,
            "author": None,
            "generated_at": None
        }

    # --------------------------------------------------------
    # STANDARD PDF INFO
    # --------------------------------------------------------

    title = extract_pdf_info_value(
        data,
        [
            "Title"
        ]
    )

    author = extract_pdf_info_value(
        data,
        [
            "Author"
        ]
    )

    generated_at = extract_pdf_info_value(
        data,
        [
            "CreationDate",
            "ModDate"
        ]
    )

    # --------------------------------------------------------
    # XMP
    # --------------------------------------------------------

    text = ""

    # Ищем начало XMP-пакета в переданном фрагменте
    xmp_start = data.find(b"<?xpacket")
    if xmp_start == -1:
        xmp_start = data.find(b"<x:xmpmeta")
    if xmp_start == -1:
        xmp_start = data.find(b"<rdf:RDF")

    if xmp_start != -1:
        xmp_data = data[xmp_start:]

        # Учитываем BOM и типичные кодировки XML
        if xmp_data.startswith(b"\xfe\xff"):
            text = xmp_data.decode("utf-16-be", errors="replace")
        elif xmp_data.startswith(b"\xff\xfe"):
            text = xmp_data.decode("utf-16-le", errors="replace")
        else:
            text = xmp_data.decode("utf-8", errors="replace")

    xmp_metadata = extract_pdf_xmp_metadata(
        text
    )

    title = (
        title
        or xmp_metadata["title"]
    )

    author = (
        author
        or xmp_metadata["author"]
    )

    generated_at = (
        xmp_metadata["published"]
        or xmp_metadata["date"]
        or generated_at
    )

    return {
        "title": title,
        "author": author,
        "generated_at": generated_at
    }

async def get_pdf_metadata(
    client,
    message
):
    """
    Получает метаданные PDF.

    Использует:

        1. стандартные PDF metadata
        2. XMP/XML metadata
    """

    file_size = message.document.size

    # --------------------------------------------------------
    # Берём начало PDF
    # --------------------------------------------------------

    first_data = await download_part(
        message,
        0,
        min(
            file_size,
            PDF_METADATA_CHUNK_SIZE
        ),
        client
    )

    metadata = extract_pdf_metadata_from_bytes(
        first_data
    )

    # --------------------------------------------------------
    # Если не нашли — берём конец PDF
    # --------------------------------------------------------

    if not (
            metadata["title"]
            and metadata["author"]
            and metadata["generated_at"]
    ):
        tail_offset = max(
            0,
            file_size - PDF_METADATA_CHUNK_SIZE
        )

        tail_data = await download_part(
            message,
            tail_offset,
            min(
                file_size,
                PDF_METADATA_CHUNK_SIZE
            ),
            client
        )

        tail_metadata = extract_pdf_metadata_from_bytes(
            tail_data
        )

        metadata["title"] = (
                metadata["title"]
                or tail_metadata["title"]
        )

        metadata["author"] = (
                metadata["author"]
                or tail_metadata["author"]
        )

        metadata["generated_at"] = (
                metadata["generated_at"]
                or tail_metadata["generated_at"]
        )

    # --------------------------------------------------------
    # TITLE FALLBACK
    # --------------------------------------------------------

    if not metadata["title"]:

        filename = (
            message.file.name
            or ""
        )

        metadata["title"] = clean_text(
            Path(
                filename
            ).stem.replace(
                "_",
                " "
            )
        )

    return metadata