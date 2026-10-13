# ============================================================
# EPUB
# ============================================================
import re
from metadata.common import extract_tag_value, clean_text, get_zip_entries, download_zip_entry, format_datetime


def extract_epub_metadata(
    opf_data
):
    """
    Извлекает метаданные EPUB из OPF.

    title
    author
    generated_at

    generated_at здесь соответствует dc:date,
    то есть дате, указанной в метаданных EPUB.
    """

    text = opf_data.decode(
        "utf-8",
        errors="replace"
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = extract_tag_value(
        text,
        "title"
    )

    # --------------------------------------------------------
    # AUTHOR
    # --------------------------------------------------------

    author_match = re.search(
        r"<(?:[\w.-]+:)?creator\b[^>]*>"
        r"(.*?)"
        r"</(?:[\w.-]+:)?creator>",
        text,
        re.IGNORECASE | re.DOTALL
    )

    author = None

    if author_match:

        author = clean_text(
            author_match.group(1)
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    generated_at = None

    date_match = re.search(
        r"<(?:[\w.-]+:)?date\b[^>]*>"
        r"(.*?)"
        r"</(?:[\w.-]+:)?date>",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if date_match:
        generated_at = format_datetime(
            clean_text(date_match.group(1))
        )

    return {
        "title": title,
        "author": author,
        "generated_at": generated_at
    }


async def get_epub_metadata(
    client,
    message
):
    """
    Получает метаданные EPUB.

    EPUB является ZIP.
    Поэтому сначала читается только
    Central Directory.
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

    # --------------------------------------------------------
    # Ищем OPF
    # --------------------------------------------------------

    for entry in entries:

        if not entry["filename"].lower().endswith(
            ".opf"
        ):
            continue

        opf_data = await download_zip_entry(
            client,
            message,
            entry
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

    return {
        "title": None,
        "author": None,
        "generated_at": None
    }

