import asyncio
import os
import gzip
import json
import pyrogram
from pyrogram import Client
from pyrogram.raw.functions.messages import SearchCustomEmoji, GetCustomEmojiDocuments
from pyrogram.raw.types import EmojiList
from pyrogram.file_id import FileId, FileType

API_ID = 23919434
API_HASH = "afac0d6c633615f8d46fe1255c5d5efc"

def generate_html_viewer(downloaded_files):
    """Генерирует HTML файл для удобного просмотра скачанных эмодзи в браузере"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Telegram Emoji Viewer</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; background-color: #1e1e1e; color: white; padding: 20px; }
            .grid { display: flex; flex-wrap: wrap; gap: 20px; }
            .card { background: #2d2d2d; padding: 15px; border-radius: 10px; text-align: center; width: 200px; }
            .emoji-container { width: 100px; height: 100px; margin: 0 auto 15px auto; }
            video, img { max-width: 100px; max-height: 100px; }
            .info { font-size: 12px; color: #aaa; margin-bottom: 5px; word-wrap: break-word; }
            .id-text { font-family: monospace; background: #000; padding: 3px; border-radius: 3px; user-select: all; cursor: pointer; }
        </style>
    </head>
    <body>
        <h2>Найденные эмодзи</h2>
        <div class="grid">
    """
    
    for item in downloaded_files:
        file_path = item['file']
        ext = os.path.splitext(file_path)[1]
        filename = os.path.basename(file_path)
        
        html_content += f'<div class="card">'
        
        if ext == '.tgs':
            # Для TGS (Lottie) читаем распакованный JSON
            try:
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    animation_data = f.read()
                
                container_id = f"lottie_{item['id']}"
                html_content += f'<div id="{container_id}" class="emoji-container"></div>'
                html_content += f"""
                <script>
                    lottie.loadAnimation({{
                        container: document.getElementById('{container_id}'),
                        renderer: 'svg',
                        loop: true,
                        autoplay: true,
                        animationData: {animation_data}
                    }});
                </script>
                """
            except Exception as e:
                html_content += f'<div class="emoji-container">Ошибка TGS</div>'
        elif ext == '.webm':
            html_content += f'<div class="emoji-container"><video autoplay loop muted playsinline src="{filename}"></video></div>'
        else:
            html_content += f'<div class="emoji-container"><img src="{filename}"></div>'
            
        html_content += f'<div class="info">Пак: <a href="{item["url"]}" style="color: #4da6ff;" target="_blank">{item["pack"]}</a></div>'
        html_content += f'<div class="info">ID: <span class="id-text">{item["id"]}</span></div>'
        html_content += f'</div>'
        
    html_content += """
        </div>
    </body>
    </html>
    """
    
    with open("downloads/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("\n✅ Готово! Откройте файл downloads/index.html в браузере, чтобы посмотреть все эмодзи.")

async def main():
    print("Инициализация клиента...")
    # При первом запуске Pyrogram попросит ввести номер телефона и код из Telegram
    async with Client("user_session", api_id=API_ID, api_hash=API_HASH) as app:
        emoticon = "❌"
        print(f"Ищем кастомные эмодзи для: {emoticon}")
        
        # 1. Ищем эмодзи
        result = await app.invoke(
            SearchCustomEmoji(
                emoticon=emoticon,
                hash=0
            )
        )
        
        if isinstance(result, EmojiList) and result.document_id:
            doc_ids = result.document_id
            print(f"Найдено {len(doc_ids)} эмодзи. Получаем детали для первых 5...")
            
            # 2. Получаем подробную информацию о найденных эмодзи
            docs = await app.invoke(
                GetCustomEmojiDocuments(
                    document_id=doc_ids[:5]
                )
            )
            
            os.makedirs("downloads", exist_ok=True)
            downloaded_files = []
            
            for doc in docs:
                alt_emoji = ""
                pack_name = ""
                pack_url = ""
                
                # Извлекаем атрибуты документа (стикера)
                for attr in doc.attributes:
                    if hasattr(attr, 'alt'):
                        alt_emoji = attr.alt
                    if hasattr(attr, 'stickerset'):
                        # stickerset может быть InputStickerSetID или InputStickerSetShortName
                        if hasattr(attr.stickerset, 'short_name'):
                            pack_name = attr.stickerset.short_name
                        elif hasattr(attr.stickerset, 'id'):
                            # Если есть только ID, мы можем получить информацию о паке
                            try:
                                sticker_set = await app.invoke(
                                    pyrogram.raw.functions.messages.GetStickerSet(
                                        stickerset=attr.stickerset,
                                        hash=0
                                    )
                                )
                                pack_name = sticker_set.set.short_name
                            except Exception as e:
                                pack_name = f"Неизвестно (ID: {attr.stickerset.id})"
                
                print("-" * 40)
                print(f"ID (для Bot API): {doc.id}")
                print(f"Базовый эмодзи: {alt_emoji}")
                print(f"Название пака: {pack_name}")
                if pack_name and not pack_name.startswith("Неизвестно"):
                    pack_url = f"https://t.me/addstickers/{pack_name}"
                    print(f"Ссылка на пак: {pack_url}")
                
                # Определяем тип файла по mime_type
                mime_type = getattr(doc, 'mime_type', '')
                is_video = mime_type == 'video/webm'
                is_animated = mime_type == 'application/x-tgsticker'
                
                print(f"Анимированный: {is_video or is_animated} ({mime_type})")
                
                # Скачиваем эмодзи для предпросмотра
                try:
                    # Определяем расширение файла
                    if is_video:
                        ext = ".webm"
                    elif is_animated:
                        ext = ".tgs"
                    else:
                        ext = ".webp"
                        
                    file_name = f"emoji_{doc.id}{ext}"
                    
                    print(f"Скачиваем эмодзи в файл {file_name}...")
                    
                    # Для сырых объектов Document нужно использовать другой метод скачивания
                    file_id_obj = FileId(
                        file_type=FileType.STICKER,
                        dc_id=doc.dc_id,
                        media_id=doc.id,
                        access_hash=doc.access_hash,
                        file_reference=doc.file_reference
                    )
                    
                    downloaded_file = await app.download_media(file_id_obj.encode(), file_name=file_name)
                    print(f"Эмодзи сохранен: {downloaded_file}")
                    
                    downloaded_files.append({
                        "id": str(doc.id),
                        "file": downloaded_file,
                        "pack": pack_name,
                        "url": pack_url
                    })
                except Exception as e:
                    print(f"Ошибка при скачивании: {e}")
                    
            # Генерируем HTML для просмотра
            if downloaded_files:
                generate_html_viewer(downloaded_files)
        else:
            print("Эмодзи не найдены.")

if __name__ == "__main__":
    asyncio.run(main())
