# /// script
# dependencies = [
#   "mcp",
#   "pyrogram",
#   "tgcrypto"
# ]
# ///

import asyncio
import pyrogram
import os
import gzip
import webbrowser
from aiohttp import web
from mcp.server.fastmcp import FastMCP
from pyrogram import Client
from pyrogram.raw.functions.messages import SearchCustomEmoji, GetCustomEmojiDocuments
from pyrogram.raw.types import EmojiList
from pyrogram.file_id import FileId, FileType

# Инициализация MCP сервера
mcp = FastMCP("TelegramEmojiSearch")

# Получаем ключи из переменных окружения (для безопасного распространения)
TG_API_ID = os.environ.get("TG_API_ID")
TG_API_HASH = os.environ.get("TG_API_HASH")

def get_tg_client():
    """Создает и возвращает клиент Pyrogram, проверяя наличие ключей"""
    if not TG_API_ID or not TG_API_HASH:
        raise ValueError(
            "Missing Telegram API credentials. "
            "Please set TG_API_ID and TG_API_HASH environment variables in your MCP configuration (mcp.json)."
        )
    return Client("user_session", api_id=int(TG_API_ID), api_hash=TG_API_HASH)

def generate_html_viewer(downloaded_files, output_path="downloads/index.html"):
    """Генерирует HTML файл для удобного просмотра скачанных эмодзи в браузере"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Telegram Emoji Selector</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; background-color: #1e1e1e; color: white; padding: 20px; }
            .grid { display: flex; flex-wrap: wrap; gap: 20px; }
            .card { 
                background: #2d2d2d; padding: 15px; border-radius: 10px; text-align: center; width: 200px; 
                cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; border: 2px solid transparent;
            }
            .card:hover { transform: translateY(-5px); box-shadow: 0 5px 15px rgba(0,0,0,0.5); border-color: #4da6ff; }
            .emoji-container { width: 100px; height: 100px; margin: 0 auto 15px auto; display: flex; align-items: center; justify-content: center; }
            video, img { max-width: 100px; max-height: 100px; }
            .info { font-size: 12px; color: #aaa; margin-bottom: 5px; word-wrap: break-word; }
            .id-text { font-family: monospace; background: #000; padding: 3px; border-radius: 3px; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
            .status { padding: 10px; border-radius: 5px; display: none; }
            .status.success { background: #2e7d32; display: block; }
            .status.error { background: #c62828; display: block; }
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Выберите подходящий эмодзи</h2>
            <div id="status" class="status"></div>
        </div>
        <p>Кликните на карточку, чтобы выбрать эмодзи. Нейросеть автоматически получит ваш выбор.</p>
        <div class="grid">
    """
    
    for item in downloaded_files:
        file_path = item['local_file_path']
        if not file_path:
            continue
            
        ext = os.path.splitext(file_path)[1]
        filename = os.path.basename(file_path)
        
        html_content += f'<div class="card" onclick="selectEmoji(\'{item["id"]}\', \'{item["base_emoji"]}\')">'
        
        if ext == '.tgs':
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
            except Exception:
                html_content += f'<div class="emoji-container">Ошибка TGS</div>'
        elif ext == '.webm':
            html_content += f'<div class="emoji-container"><video autoplay loop muted playsinline src="{filename}"></video></div>'
        else:
            html_content += f'<div class="emoji-container"><img src="{filename}"></div>'
            
        html_content += f'<div class="info">Пак: <a href="{item["pack_url"]}" style="color: #4da6ff;" target="_blank" onclick="event.stopPropagation()">{item["pack_name"]}</a></div>'
        html_content += f'<div class="info">ID: <span class="id-text">{item["id"]}</span></div>'
        html_content += f'</div>'
        
    html_content += """
        </div>
        <script>
            async function selectEmoji(id, baseEmoji) {
                const statusEl = document.getElementById('status');
                try {
                    const response = await fetch('/select', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: id, base_emoji: baseEmoji })
                    });
                    
                    if (response.ok) {
                        statusEl.textContent = '✅ Эмодзи ' + id + ' успешно выбран! Можете закрыть вкладку.';
                        statusEl.className = 'status success';
                        
                        // Подсвечиваем выбранную карточку
                        document.querySelectorAll('.card').forEach(c => c.style.borderColor = 'transparent');
                        event.currentTarget.style.borderColor = '#4da6ff';
                        event.currentTarget.style.background = '#3d3d3d';
                    } else {
                        throw new Error('Server error');
                    }
                } catch (e) {
                    // Игнорируем ошибку CORS/Network, если сервер уже закрылся после успешного ответа
                    statusEl.textContent = '✅ Эмодзи ' + id + ' успешно выбран! Можете закрыть вкладку.';
                    statusEl.className = 'status success';
                    
                    document.querySelectorAll('.card').forEach(c => c.style.borderColor = 'transparent');
                    event.currentTarget.style.borderColor = '#4da6ff';
                    event.currentTarget.style.background = '#3d3d3d';
                }
            }
        </script>
    </body>
    </html>
    """
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return os.path.abspath(output_path)

# Глобальная переменная для хранения выбранного эмодзи
selected_emoji_future = None
web_app_runner = None
web_server_port = None

async def handle_selection(request):
    """Обработчик POST запроса от браузера с выбранным эмодзи"""
    global selected_emoji_future
    try:
        data = await request.json()
        
        if selected_emoji_future and not selected_emoji_future.done():
            selected_emoji_future.set_result(data)
            
        # Добавляем заголовки CORS для надежности
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return web.Response(text="OK", headers=headers)
    except Exception as e:
        return web.Response(status=500, text=str(e))

async def handle_options(request):
    """Обработчик OPTIONS запроса для CORS"""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    return web.Response(text="OK", headers=headers)

async def start_web_server():
    """Запускает локальный веб-сервер для отдачи статики и приема выбора"""
    global web_app_runner, web_server_port
    
    app = web.Application()
    
    # Раздаем статику из папки downloads
    os.makedirs("downloads", exist_ok=True)
    app.router.add_static('/', path='downloads', name='static')
    
    # API для приема выбора
    app.router.add_post('/select', handle_selection)
    app.router.add_options('/select', handle_options)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Порт 0 заставляет ОС автоматически выдать любой свободный порт
    site = web.TCPSite(runner, 'localhost', 0)
    await site.start()
    
    # Получаем порт, который выдала ОС
    web_server_port = site._server.sockets[0].getsockname()[1]
    web_app_runner = runner
    
    return f"http://localhost:{web_server_port}/index.html"

@mcp.tool()
async def search_and_select_emoji(
    emoticons: list[str], 
    limit: int = 10, 
    pack_name: str = None, 
    is_animated: bool = None
) -> dict:
    """
    DEFAULT TOOL FOR EMOJI SEARCH.
    Searches for custom Telegram emojis, opens a browser for the user to select one, and WAITS for the user's click.
    ALWAYS use this tool by default unless the user explicitly asks for automatic selection.
    
    Args:
        emoticons: List of base emojis to search for (e.g., ["❌", "🔴"]).
        limit: Maximum number of results per base emoji (default 10).
        pack_name: Optional. Filter by a specific sticker pack name.
        is_animated: Optional. True for animated/video only, False for static only.
        
    Returns:
        Dictionary containing the ID of the emoji selected by the user.
    """
    global selected_emoji_future, web_app_runner, web_server_port
    
    try:
        app = get_tg_client()
    except ValueError as e:
        return {"error": str(e)}
    
    # Запускаем клиент, если он еще не запущен
    async with app:
        try:
            all_doc_ids = []
            
            # Ищем эмодзи для каждого смайла из списка
            for emoticon in emoticons:
                result = await app.invoke(
                    SearchCustomEmoji(
                        emoticon=emoticon,
                        hash=0
                    )
                )
                if isinstance(result, EmojiList) and result.document_id:
                    all_doc_ids.extend(result.document_id[:limit])
            
            if not all_doc_ids:
                return {"error": "No emojis found for the given base emoticons"}
                
            # Убираем дубликаты
            all_doc_ids = list(dict.fromkeys(all_doc_ids))
            
            # Получаем подробную информацию о найденных эмодзи
            docs = await app.invoke(
                GetCustomEmojiDocuments(
                    document_id=all_doc_ids
                )
            )
            
            emoji_details = []
            for doc in docs:
                alt_emoji = ""
                current_pack_name = ""
                
                # Извлекаем атрибуты документа (стикера)
                for attr in doc.attributes:
                    if hasattr(attr, 'alt'):
                        alt_emoji = attr.alt
                    if hasattr(attr, 'stickerset'):
                        if hasattr(attr.stickerset, 'short_name'):
                            current_pack_name = attr.stickerset.short_name
                        elif hasattr(attr.stickerset, 'id'):
                            try:
                                sticker_set = await app.invoke(
                                    pyrogram.raw.functions.messages.GetStickerSet(
                                        stickerset=attr.stickerset,
                                        hash=0
                                    )
                                )
                                current_pack_name = sticker_set.set.short_name
                            except Exception:
                                pass
                        
                # Определяем тип файла по mime_type
                mime_type = getattr(doc, 'mime_type', '')
                is_video_doc = mime_type == 'video/webm'
                is_animated_doc = mime_type == 'application/x-tgsticker'
                is_anim_or_video = is_video_doc or is_animated_doc
                
                # --- ПРИМЕНЯЕМ ФИЛЬТРЫ ---
                if pack_name and pack_name.lower() not in current_pack_name.lower():
                    continue
                    
                if is_animated is not None:
                    if is_animated and not is_anim_or_video:
                        continue
                    if not is_animated and is_anim_or_video:
                        continue
                
                # Скачиваем файл для предпросмотра
                local_path = ""
                try:
                    if is_video_doc:
                        ext = ".webm"
                    elif is_animated_doc:
                        ext = ".tgs"
                    else:
                        ext = ".webp"
                        
                    file_name = f"emoji_{doc.id}{ext}"
                    
                    # Создаем директорию для скачивания, если её нет
                    os.makedirs("downloads", exist_ok=True)
                    
                    file_id_obj = FileId(
                        file_type=FileType.STICKER,
                        dc_id=doc.dc_id,
                        media_id=doc.id,
                        access_hash=doc.access_hash,
                        file_reference=doc.file_reference
                    )
                    
                    downloaded_file = await app.download_media(file_id_obj.encode(), file_name=file_name)
                    if downloaded_file:
                        local_path = os.path.abspath(downloaded_file)
                except Exception as e:
                    print(f"Download error {doc.id}: {e}")
                        
                emoji_details.append({
                    "id": str(doc.id),
                    "base_emoji": alt_emoji,
                    "pack_name": current_pack_name,
                    "pack_url": f"https://t.me/addstickers/{current_pack_name}" if current_pack_name else "",
                    "is_animated": is_anim_or_video,
                    "local_file_path": local_path
                })
                
            if not emoji_details:
                return {"error": "No emojis left after applying filters"}
                
            # Генерируем HTML галерею
            generate_html_viewer(emoji_details)
            
            # Запускаем веб-сервер, если он еще не запущен
            if not web_app_runner:
                url = await start_web_server()
            else:
                url = f"http://localhost:{web_server_port}/index.html"
                
            # Открываем браузер
            webbrowser.open(url)
            
            # Создаем Future для ожидания выбора пользователя
            selected_emoji_future = asyncio.Future()
            
            # Ждем, пока пользователь не кликнет на эмодзи в браузере (таймаут 5 минут)
            try:
                selected_data = await asyncio.wait_for(selected_emoji_future, timeout=300.0)
                
                # Даем серверу немного времени на отправку ответа браузеру перед завершением
                await asyncio.sleep(0.5)
                
                return {
                    "status": "success",
                    "message": "User successfully selected an emoji",
                    "selected_emoji_id": selected_data["id"],
                    "base_emoji": selected_data["base_emoji"]
                }
            except asyncio.TimeoutError:
                return {"error": "Timeout: User did not select an emoji within 5 minutes"}
            
        except Exception as e:
            return {"error": f"Search error: {str(e)}"}

@mcp.tool()
async def search_emoji_auto(
    emoticons: list[str], 
    limit: int = 5, 
    pack_name: str = None, 
    is_animated: bool = None
) -> dict:
    """
    NON-INTERACTIVE TOOL.
    Searches for custom Telegram emojis and returns the results directly without user interaction.
    ONLY use this tool if the user EXPLICITLY asks to pick an emoji automatically without asking them, 
    or if they just want a raw list of available options.
    
    Args:
        emoticons: List of base emojis to search for (e.g., ["❌", "🔴"]).
        limit: Maximum number of results per base emoji (default 5).
        pack_name: Optional. Filter by a specific sticker pack name.
        is_animated: Optional. True for animated/video only, False for static only.
        
    Returns:
        Dictionary containing a list of matching emojis with their IDs and metadata.
    """
    try:
        app = get_tg_client()
    except ValueError as e:
        return {"error": str(e)}
    
    async with app:
        try:
            all_doc_ids = []
            
            for emoticon in emoticons:
                result = await app.invoke(
                    SearchCustomEmoji(emoticon=emoticon, hash=0)
                )
                if isinstance(result, EmojiList) and result.document_id:
                    all_doc_ids.extend(result.document_id[:limit])
            
            if not all_doc_ids:
                return {"error": "No emojis found"}
                
            all_doc_ids = list(dict.fromkeys(all_doc_ids))
            
            docs = await app.invoke(GetCustomEmojiDocuments(document_id=all_doc_ids))
            
            emoji_details = []
            for doc in docs:
                alt_emoji = ""
                current_pack_name = ""
                
                for attr in doc.attributes:
                    if hasattr(attr, 'alt'):
                        alt_emoji = attr.alt
                    if hasattr(attr, 'stickerset'):
                        if hasattr(attr.stickerset, 'short_name'):
                            current_pack_name = attr.stickerset.short_name
                        elif hasattr(attr.stickerset, 'id'):
                            try:
                                sticker_set = await app.invoke(
                                    pyrogram.raw.functions.messages.GetStickerSet(
                                        stickerset=attr.stickerset, hash=0
                                    )
                                )
                                current_pack_name = sticker_set.set.short_name
                            except Exception:
                                pass
                        
                mime_type = getattr(doc, 'mime_type', '')
                is_anim_or_video = mime_type in ('video/webm', 'application/x-tgsticker')
                
                if pack_name and pack_name.lower() not in current_pack_name.lower():
                    continue
                    
                if is_animated is not None:
                    if is_animated and not is_anim_or_video:
                        continue
                    if not is_animated and is_anim_or_video:
                        continue
                        
                emoji_details.append({
                    "id": str(doc.id),
                    "base_emoji": alt_emoji,
                    "pack_name": current_pack_name,
                    "is_animated": is_anim_or_video
                })
                
            if not emoji_details:
                return {"error": "No emojis left after applying filters"}
                
            return {
                "status": "success",
                "count": len(emoji_details),
                "results": emoji_details
            }
            
        except Exception as e:
            return {"error": f"Search error: {str(e)}"}

if __name__ == "__main__":
    # Запуск MCP сервера
    mcp.run()
