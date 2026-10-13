from pathlib import Path

from metadata.fb2 import get_fb2_metadata
from metadata.epub import get_epub_metadata
from metadata.zip import get_zip_metadata
from metadata.pdf import get_pdf_metadata

async def get_book_metadata(
    client,
    chat_id,
    message_id
):
    """
    Главная функция.

    Передаём:

        client
        chat_id
        message_id

    Получаем:

        {
            "title": "...",
            "author": "...",
            "generated_at": "...",
            "format": "fb2"
        }
    """

    # --------------------------------------------------------
    # Получаем сообщение
    # --------------------------------------------------------

    message = await client.get_messages(
        chat_id,
        ids=message_id
    )

    if not message:

        raise ValueError(
            "Сообщение не найдено"
        )

    if not message.document:

        raise ValueError(
            "Сообщение не содержит документ"
        )

    # --------------------------------------------------------
    # Получаем имя файла
    # --------------------------------------------------------

    filename = (
        message.file.name
        or ""
    )

    extension = Path(
        filename
    ).suffix.lower()

    # --------------------------------------------------------
    # FB2
    # --------------------------------------------------------

    if extension == ".fb2":

        metadata = await get_fb2_metadata(
            client,
            message
        )

    # --------------------------------------------------------
    # EPUB
    # --------------------------------------------------------

    elif extension == ".epub":

        metadata = await get_epub_metadata(
            client,
            message
        )

    # --------------------------------------------------------
    # ZIP
    # --------------------------------------------------------

    elif extension == ".zip":

        metadata = await get_zip_metadata(
            client,
            message
        )

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    elif extension == ".pdf":

        metadata = await get_pdf_metadata(
            client,
            message
        )


    # --------------------------------------------------------
    # Другой формат
    # --------------------------------------------------------

    else:

        raise ValueError(
            f"Неподдерживаемый формат: {extension or 'неизвестен'}"
        )

    # --------------------------------------------------------
    # Возвращаем результат
    # --------------------------------------------------------

    return {
        "title": metadata["title"],
        "author": metadata["author"],
        "generated_at": metadata["generated_at"],
        "format": extension.lstrip(".")
    }