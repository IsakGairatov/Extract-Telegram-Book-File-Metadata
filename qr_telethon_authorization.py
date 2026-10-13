import asyncio
import os

import qrcode
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")


async def main():
    client = TelegramClient("userbot", API_ID, API_HASH)

    await client.connect()

    if await client.is_user_authorized():
        print("Уже авторизован!")
        await client.disconnect()
        return

    qr_login = await client.qr_login()

    qr = qrcode.make(qr_login.url)
    qr.save("telegram_login.png")

    print("QR-код сохранён в telegram_login.png")
    print("Открой файл и отсканируй его через Telegram → Настройки → Устройства.")


    try:
        await qr_login.wait()
        print("Авторизация успешна!")

    except Exception as e:
        print(f"Ошибка: {type(e).__name__}: {e}")

        await client.sign_in(password="bonbon_12")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())