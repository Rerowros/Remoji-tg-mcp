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
from dotenv import load_dotenv, set_key

# Загружаем переменные окружения из .env
load_dotenv()

# Инициализация MCP сервера
mcp = FastMCP("TelegramEmojiSearch")

# Получаем ключи
TG_API_ID = os.environ.get("TG_API_ID")
TG_API_HASH = os.environ.get("TG_API_HASH")
ENV_FILE = ".env"

def get_tg_client():
    """Создает и возвращает клиент Pyrogram, проверяя наличие ключей"""
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    
    if not api_id or not api_hash:
        return None
        
    try:
        return Client("user_session", api_id=int(api_id), api_hash=api_hash)
    except (ValueError, TypeError):
        return None

def generate_html_viewer(downloaded_files, output_path="downloads/index.html"):
    """Генерирует HTML файл для удобного просмотра скачанных эмодзи в браузере"""
    # Группируем по базовому эмодзи
    grouped_files = {}
    for item in downloaded_files:
        base = item.get('base_emoji', 'Other')
        if base not in grouped_files:
            grouped_files[base] = []
        grouped_files[base].append(item)

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Telegram Emoji Selector</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; background-color: #1e1e1e; color: white; padding: 20px; }
            .group-section { margin-bottom: 40px; border-bottom: 1px solid #444; padding-bottom: 20px; }
            .group-title { font-size: 24px; margin-bottom: 15px; display: flex; align-items: center; gap: 10px; }
            .grid { display: flex; flex-wrap: wrap; gap: 20px; }
            .card { 
                background: #2d2d2d; padding: 15px; border-radius: 10px; text-align: center; width: 200px; 
                cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; border: 2px solid transparent;
                position: relative;
            }
            .card:hover { transform: translateY(-5px); box-shadow: 0 5px 15px rgba(0,0,0,0.5); border-color: #4da6ff; }
            .card.selected { border-color: #4da6ff; background: #3d3d3d; }
            .emoji-container { width: 100px; height: 100px; margin: 0 auto 15px auto; display: flex; align-items: center; justify-content: center; }
            video, img { max-width: 100px; max-height: 100px; }
            .info { font-size: 12px; color: #aaa; margin-bottom: 5px; word-wrap: break-word; }
            .id-text { font-family: monospace; background: #000; padding: 3px; border-radius: 3px; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; position: sticky; top: 0; background: #1e1e1e; z-index: 100; padding: 10px 0; }
            .status { padding: 10px; border-radius: 5px; display: none; }
            .status.success { background: #2e7d32; display: block; }
            .status.error { background: #c62828; display: block; }
            .checkbox-container { position: absolute; top: 10px; right: 10px; pointer-events: none; }
            .checkbox-container input { width: 20px; height: 20px; pointer-events: auto; cursor: pointer; }
            .btn { background: #4da6ff; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; }
            .btn:hover { background: #3d8fdf; }
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <h2>Выберите подходящие эмодзи</h2>
                <p>Выберите по одному или несколько вариантов для каждого запроса и нажмите "Подтвердить выбор".</p>
            </div>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div id="status" class="status"></div>
                <button id="confirm-btn" class="btn" onclick="submitSelections()">Подтвердить выбор</button>
            </div>
        </div>
        
        <div id="main-content">
    """
    
    for base_emoji, items in grouped_files.items():
        html_content += f"""
        <div class="group-section" data-base="{base_emoji}">
            <div class="group-title">Поиск для: <span style="font-size: 32px;">{base_emoji}</span></div>
            <div class="grid">
        """
        
        for item in items:
            file_path = item['local_file_path']
            if not file_path:
                continue
                
            ext = os.path.splitext(file_path)[1]
            filename = os.path.basename(file_path)
            
            card_id = f"card_{item['id']}"
            html_content += f"""
            <div id="{card_id}" class="card" onclick="toggleSelection('{item['id']}', '{base_emoji}')">
                <div class="checkbox-container">
                    <input type="checkbox" id="check_{item['id']}" data-id="{item['id']}" data-base="{base_emoji}" onclick="event.stopPropagation(); updateCardStyle('{item['id']}')">
                </div>
            """
            
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
        </div>
        """
        
    html_content += """
        </div>
        <script>
            function toggleSelection(id, baseEmoji) {
                const checkbox = document.getElementById('check_' + id);
                checkbox.checked = !checkbox.checked;
                updateCardStyle(id);
            }
            
            function updateCardStyle(id) {
                const card = document.getElementById('card_' + id);
                const checkbox = document.getElementById('check_' + id);
                if (checkbox.checked) {
                    card.classList.add('selected');
                } else {
                    card.classList.remove('selected');
                }
            }

            async function submitSelections() {
                const statusEl = document.getElementById('status');
                const btn = document.getElementById('confirm-btn');
                
                const selected = [];
                document.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
                    selected.push({
                        id: cb.getAttribute('data-id'),
                        base_emoji: cb.getAttribute('data-base')
                    });
                });
                
                if (selected.length === 0) {
                    alert('Пожалуйста, выберите хотя бы один эмодзи.');
                    return;
                }
                
                btn.disabled = true;
                btn.textContent = 'Отправка...';
                
                try {
                    const response = await fetch('/select', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ selections: selected })
                    });
                    
                    if (response.ok) {
                        statusEl.textContent = '✅ ' + selected.length + ' эмодзи успешно выбрано!';
                        statusEl.className = 'status success';
                        btn.textContent = 'Готово';
                    } else {
                        throw new Error('Server error');
                    }
                } catch (e) {
                    statusEl.textContent = '✅ Выбор отправлен! Можете закрыть вкладку.';
                    statusEl.className = 'status success';
                    btn.textContent = 'Готово';
                }
            }
        </script>
    </body>
    </html>
    """
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return os.path.abspath(output_path)

# Глобальные переменные для хранения выбранного эмодзи и статуса конфига
selected_emoji_future = None
config_update_future = None
web_app_runner = None
web_server_port = None

async def handle_config_get(request):
    """Отображает страницу настройки API"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Telegram API Setup</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #1e1e1e; color: white; padding: 40px; display: flex; justify-content: center; }
            .container { background: #2d2d2d; padding: 30px; border-radius: 10px; width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
            h2 { margin-top: 0; color: #4da6ff; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 5px; color: #aaa; }
            input { width: 100%; padding: 10px; background: #1e1e1e; border: 1px solid #444; border-radius: 5px; color: white; box-sizing: border-box; }
            .btn { background: #4da6ff; color: white; border: none; padding: 12px; width: 100%; border-radius: 5px; cursor: pointer; font-weight: bold; margin-top: 10px; }
            .btn:hover { background: #3d8fdf; }
            .info { font-size: 13px; color: #888; margin-top: 15px; line-height: 1.4; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Настройка Telegram API</h2>
            <form action="/config" method="post">
                <div class="form-group">
                    <label>API ID</label>
                    <input type="text" name="api_id" placeholder="Например: 1234567" required>
                </div>
                <div class="form-group">
                    <label>API HASH</label>
                    <input type="text" name="api_hash" placeholder="Например: abc123def456..." required>
                </div>
                <button type="submit" class="btn">Сохранить и продолжить</button>
            </form>
            <div class="info">
                Получить API ID и API HASH можно на сайте <a href="https://my.telegram.org/apps" target="_blank" style="color: #4da6ff;">my.telegram.org</a>.
                Эти данные будут сохранены локально в файле .env.
            </div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def handle_config_post(request):
    """Обрабатывает сохранение конфига"""
    global config_update_future
    data = await request.post()
    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    
    if api_id and api_hash:
        # Сохраняем в .env
        set_key(ENV_FILE, "TG_API_ID", str(api_id))
        set_key(ENV_FILE, "TG_API_HASH", str(api_hash))
        
        # Обновляем переменные окружения в текущем процессе
        os.environ["TG_API_ID"] = str(api_id)
        os.environ["TG_API_HASH"] = str(api_hash)
        
        if config_update_future and not config_update_future.done():
            config_update_future.set_result(True)
            
        return web.Response(text="<h1>Настройки сохранены!</h1><p>Вы можете закрыть эту вкладку, MCP сервер сейчас продолжит работу.</p><script>setTimeout(()=>window.close(), 3000)</script>", content_type='text/html')
    
    return web.Response(status=400, text="Invalid data")

async def handle_selection(request):
    """Обработчик POST запроса от браузера с выбранными эмодзи"""
    global selected_emoji_future
    try:
        data = await request.json()
        
        if selected_emoji_future and not selected_emoji_future.done():
            selected_emoji_future.set_result(data)
            
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
    app.router.add_static('/static', path='downloads', name='static')
    
    # API для приема выбора
    app.router.add_post('/select', handle_selection)
    app.router.add_options('/select', handle_options)
    
    # Роуты для конфигурации
    app.router.add_get('/config', handle_config_get)
    app.router.add_post('/config', handle_config_post)
    
    # Редирект с корня на index.html
    async def index_redir(request):
        return web.HTTPFound('/static/index.html')
    app.router.add_get('/', index_redir)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    
    web_server_port = site._server.sockets[0].getsockname()[1]
    web_app_runner = runner
    
    return f"http://127.0.0.1:{web_server_port}"

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
        Dictionary containing the IDs of the emojis selected by the user.
    """
    global selected_emoji_future, config_update_future, web_app_runner, web_server_port
    
    # Проверяем наличие конфигурации
    app = get_tg_client()
    if not app:
        # Запускаем сервер если еще не запущен
        if not web_app_runner:
            base_url = await start_web_server()
        else:
            base_url = f"http://127.0.0.1:{web_server_port}"
            
        # Открываем страницу конфига
        webbrowser.open(f"{base_url}/config")
        
        # Ждем обновления конфига
        config_update_future = asyncio.Future()
        try:
            await asyncio.wait_for(config_update_future, timeout=300.0)
            app = get_tg_client()
            if not app:
                return {"error": "Failed to initialize Telegram client after config update"}
        except asyncio.TimeoutError:
            return {"error": "Timeout waiting for API configuration"}

    # Запускаем клиент, если он еще не запущен
    async with app:
        try:
            all_doc_ids = []
            
            # Ищем эмодзи для каждого смайла из списка
            for emoticon in emoticons:
                try:
                    result = await app.invoke(
                        SearchCustomEmoji(
                            emoticon=emoticon,
                            hash=0
                        )
                    )
                    if isinstance(result, EmojiList) and result.document_id:
                        all_doc_ids.extend(result.document_id[:limit])
                except pyrogram.errors.Unauthorized:
                    # Если ключ неверный, просим перенастроить
                    if not web_app_runner:
                        base_url = await start_web_server()
                    else:
                        base_url = f"http://127.0.0.1:{web_server_port}"
                    webbrowser.open(f"{base_url}/config")
                    return {"error": "Telegram API credentials are invalid. Please update them in the opened browser window and try again."}
            
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
                base_url = await start_web_server()
            else:
                base_url = f"http://127.0.0.1:{web_server_port}"
                
            # Открываем браузер (редирект на index.html через /)
            webbrowser.open(f"{base_url}/static/index.html")
            
            # Создаем Future для ожидания выбора пользователя
            selected_emoji_future = asyncio.Future()
            
            # Ждем, пока пользователь не подтвердит выбор (таймаут 5 минут)
            try:
                selected_data = await asyncio.wait_for(selected_emoji_future, timeout=300.0)
                
                # Даем серверу немного времени на отправку ответа браузеру перед завершением
                await asyncio.sleep(0.5)
                
                return {
                    "status": "success",
                    "message": f"User successfully selected {len(selected_data.get('selections', []))} emojis",
                    "selected_emojis": selected_data.get("selections", [])
                }
            except asyncio.TimeoutError:
                return {"error": "Timeout: User did not select any emoji within 5 minutes"}
            
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
    global web_app_runner, web_server_port, config_update_future
    
    app = get_tg_client()
    if not app:
        # Просим настроить API
        if not web_app_runner:
            base_url = await start_web_server()
        else:
            base_url = f"http://127.0.0.1:{web_server_port}"
        webbrowser.open(f"{base_url}/config")
        
        config_update_future = asyncio.Future()
        try:
            await asyncio.wait_for(config_update_future, timeout=300.0)
            app = get_tg_client()
            if not app:
                return {"error": "API not configured"}
        except asyncio.TimeoutError:
            return {"error": "Timeout waiting for API configuration"}
    
    async with app:
        try:
            all_doc_ids = []
            
            for emoticon in emoticons:
                try:
                    result = await app.invoke(
                        SearchCustomEmoji(emoticon=emoticon, hash=0)
                    )
                    if isinstance(result, EmojiList) and result.document_id:
                        all_doc_ids.extend(result.document_id[:limit])
                except pyrogram.errors.Unauthorized:
                    return {"error": "Invalid API credentials. Please run search_and_select_emoji to update them."}
            
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

def main():
    """Точка входа для запуска MCP сервера"""
    mcp.run()

if __name__ == "__main__":
    main()
