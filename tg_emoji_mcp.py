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
import logging
import sys
import json
from aiohttp import web, ClientSession
from mcp.server.fastmcp import FastMCP
from pyrogram import Client
from pyrogram.raw.functions.messages import SearchCustomEmoji, GetCustomEmojiDocuments
from pyrogram.raw.types import EmojiList
from pyrogram.file_id import FileId, FileType
from dotenv import load_dotenv, set_key

# Текущая версия
VERSION = "0.1.3"
PACKAGE_NAME = "remoji-tg-mcp"

# Настройка логирования в stderr, чтобы не засорять stdout (используется MCP)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

# Отключаем баннер Pyrogram и другие шумные логи
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

logger = logging.getLogger("tg-emoji-mcp")

# Загружаем переменные окружения из .env
load_dotenv()

# Инициализация MCP сервера
mcp = FastMCP("TelegramEmojiSearch")

# Константы
ENV_FILE = ".env"

# Глобальные переменные для управления состоянием авторизации и веб-сервера
selected_emoji_future = None
config_update_future = None
web_app_runner = None
web_server_port = None

# Состояние процесса входа в Telegram
auth_session = {
    "client": None,
    "phone": None,
    "phone_code_hash": None,
    "step": "config", # config -> phone -> code -> password (optional) -> done
    "error": None
}

async def check_for_updates():
    """Проверяет наличие новой версии на PyPI"""
    try:
        async with ClientSession() as session:
            async with session.get(f"https://pypi.org/pypi/{PACKAGE_NAME}/json", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    latest_version = data["info"]["version"]
                    if latest_version != VERSION:
                        logger.warning(f"\n" + "!"*40 + 
                                     f"\nНОВАЯ ВЕРСИЯ ДОСТУПНА: {latest_version} (у вас {VERSION})" +
                                     f"\nОбновите командой: uv tool upgrade {PACKAGE_NAME}" +
                                     f"\n" + "!"*40)
                    else:
                        logger.info(f"Версия актуальна: {VERSION}")
    except Exception as e:
        logger.debug(f"Ошибка проверки обновлений: {e}")

def get_tg_client():
    """Создает и возвращает клиент Pyrogram, используя пароль для шифрования сессии, если он есть"""
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    session_password = os.environ.get("SESSION_PASSWORD") # Можно добавить в .env для защиты .session файла
    
    if not api_id or not api_hash:
        return None
        
    try:
        # Если задан SESSION_PASSWORD, файл user_session.session будет зашифрован
        return Client(
            "user_session", 
            api_id=int(api_id), 
            api_hash=api_hash, 
            password=session_password, 
            device_model="MCP Server"
        )
    except (ValueError, TypeError):
        return None

async def ensure_authorized():
    """Проверяет авторизацию и запускает веб-интерфейс для входа, если нужно"""
    global config_update_future, auth_session
    
    client = get_tg_client()
    if not client:
        auth_session["step"] = "config"
        await open_auth_page()
        return False

    try:
        await client.connect()
        if await client.get_me():
            await client.disconnect()
            return True
        else:
            auth_session["step"] = "phone"
            auth_session["client"] = client
            await open_auth_page()
            return False
    except Exception as e:
        logger.error(f"Auth check error: {e}")
        auth_session["step"] = "config"
        await open_auth_page()
        return False
    finally:
        if client.is_connected:
            await client.disconnect()

async def open_auth_page():
    """Открывает страницу авторизации в браузере"""
    global web_app_runner, web_server_port, config_update_future
    
    if not web_app_runner:
        base_url = await start_web_server()
    else:
        base_url = f"http://127.0.0.1:{web_server_port}"
        
    webbrowser.open(f"{base_url}/auth")
    
    if not config_update_future or config_update_future.done():
        config_update_future = asyncio.Future()

async def handle_auth_get(request):
    """Отображает страницу авторизации в зависимости от текущего шага"""
    step = auth_session["step"]
    error_msg = f'<p style="color: #ff4d4d;">Error: {auth_session["error"]}</p>' if auth_session["error"] else ""
    
    content = ""
    if step == "config":
        content = """
            <h2>1. Настройка API</h2>
            <form action="/auth/config" method="post">
                <div class="form-group">
                    <label>API ID</label>
                    <input type="text" name="api_id" placeholder="1234567" required>
                </div>
                <div class="form-group">
                    <label>API HASH</label>
                    <input type="text" name="api_hash" placeholder="abc123def..." required>
                </div>
                <button type="submit" class="btn">Сохранить</button>
            </form>
        """
    elif step == "phone":
        content = """
            <h2>2. Номер телефона</h2>
            <form action="/auth/phone" method="post">
                <div class="form-group">
                    <label>Телефон (в международном формате)</label>
                    <input type="text" name="phone" placeholder="+79991234567" required>
                </div>
                <button type="submit" class="btn">Отправить код</button>
            </form>
        """
    elif step == "code":
        content = """
            <h2>3. Код подтверждения</h2>
            <form action="/auth/code" method="post">
                <div class="form-group">
                    <label>Код из Telegram</label>
                    <input type="text" name="code" placeholder="12345" required>
                </div>
                <button type="submit" class="btn">Войти</button>
            </form>
        """
    elif step == "password":
        content = """
            <h2>4. Двухфакторная аутентификация</h2>
            <form action="/auth/password" method="post">
                <div class="form-group">
                    <label>Облачный пароль</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit" class="btn">Подтвердить</button>
            </form>
        """
    else:
        content = "<h2>✅ Авторизация успешна!</h2><p>Теперь вы можете использовать MCP инструменты. Эту вкладку можно закрыть.</p>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Telegram Auth</title>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #1e1e1e; color: white; padding: 40px; display: flex; justify-content: center; }}
            .container {{ background: #2d2d2d; padding: 30px; border-radius: 10px; width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            h2 {{ margin-top: 0; color: #4da6ff; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; margin-bottom: 5px; color: #aaa; }}
            input {{ width: 100%; padding: 10px; background: #1e1e1e; border: 1px solid #444; border-radius: 5px; color: white; box-sizing: border-box; }}
            .btn {{ background: #4da6ff; color: white; border: none; padding: 12px; width: 100%; border-radius: 5px; cursor: pointer; font-weight: bold; margin-top: 10px; }}
            .btn:hover {{ background: #3d8fdf; }}
        </style>
    </head>
    <body>
        <div class="container">
            {error_msg}
            {content}
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def handle_auth_config(request):
    data = await request.post()
    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    if api_id and api_hash:
        set_key(ENV_FILE, "TG_API_ID", str(api_id))
        set_key(ENV_FILE, "TG_API_HASH", str(api_hash))
        os.environ["TG_API_ID"] = str(api_id)
        os.environ["TG_API_HASH"] = str(api_hash)
        auth_session["step"] = "phone"
        auth_session["error"] = None
        auth_session["client"] = get_tg_client()
    return web.HTTPFound('/auth')

async def handle_auth_phone(request):
    data = await request.post()
    phone = data.get('phone')
    if phone:
        auth_session["phone"] = phone
        client = auth_session["client"]
        try:
            await client.connect()
            code_obj = await client.send_code(phone)
            auth_session["phone_code_hash"] = code_obj.phone_code_hash
            auth_session["step"] = "code"
            auth_session["error"] = None
        except Exception as e:
            auth_session["error"] = str(e)
        finally:
            await client.disconnect()
    return web.HTTPFound('/auth')

async def handle_auth_code(request):
    data = await request.post()
    code = data.get('code')
    if code:
        client = auth_session["client"]
        try:
            await client.connect()
            await client.sign_in(auth_session["phone"], auth_session["phone_code_hash"], code)
            auth_session["step"] = "done"
            auth_session["error"] = None
            if config_update_future and not config_update_future.done():
                config_update_future.set_result(True)
        except pyrogram.errors.SessionPasswordNeeded:
            auth_session["step"] = "password"
            auth_session["error"] = None
        except Exception as e:
            auth_session["error"] = str(e)
        finally:
            await client.disconnect()
    return web.HTTPFound('/auth')

async def handle_auth_password(request):
    data = await request.post()
    password = data.get('password')
    if password:
        client = auth_session["client"]
        try:
            await client.connect()
            await client.check_password(password)
            auth_session["step"] = "done"
            auth_session["error"] = None
            if config_update_future and not config_update_future.done():
                config_update_future.set_result(True)
        except Exception as e:
            auth_session["error"] = str(e)
        finally:
            await client.disconnect()
    return web.HTTPFound('/auth')

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
    
    # Роуты для авторизации
    app.router.add_get('/auth', handle_auth_get)
    app.router.add_post('/auth/config', handle_auth_config)
    app.router.add_post('/auth/phone', handle_auth_phone)
    app.router.add_post('/auth/code', handle_auth_code)
    app.router.add_post('/auth/password', handle_auth_password)
    
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
    
    # Проверка обновлений при первом вызове инструмента
    await check_for_updates()
    
    # Проверяем авторизацию
    if not await ensure_authorized():
        try:
            await asyncio.wait_for(config_update_future, timeout=600.0)
        except asyncio.TimeoutError:
            return {"error": "Timeout waiting for authorization"}

    app = get_tg_client()
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
                    auth_session["step"] = "phone"
                    await open_auth_page()
                    return {"error": "Telegram session expired. Please re-authorize in the opened browser window."}
            
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
                    logger.error(f"Download error {doc.id}: {e}")
                        
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
    global config_update_future
    
    # Проверка обновлений
    await check_for_updates()
    
    if not await ensure_authorized():
        try:
            await asyncio.wait_for(config_update_future, timeout=600.0)
        except asyncio.TimeoutError:
            return {"error": "Timeout waiting for authorization"}
    
    app = get_tg_client()
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
                    return {"error": "Session expired. Run search_and_select_emoji to re-authorize."}
            
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
