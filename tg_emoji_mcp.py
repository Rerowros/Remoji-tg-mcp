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
import re
import shutil
from aiohttp import web, ClientSession
from mcp.server.fastmcp import FastMCP
from pyrogram import Client
from pyrogram.raw.functions.messages import SearchCustomEmoji, GetCustomEmojiDocuments
from pyrogram.raw.types import EmojiList
from pyrogram.file_id import FileId, FileType
from dotenv import load_dotenv, set_key

# Текущая версия
VERSION = "0.1.7"
PACKAGE_NAME = "remoji-tg-mcp"

# Принудительная установка UTF-8 для вывода в консоль (Windows fix)
if sys.platform == "win32":
    import io
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

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
DOWNLOADS_DIR = "downloads"

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

# --- Вспомогательные функции ---

def cleanup_downloads():
    """Удаляет старые скачанные файлы эмодзи при запуске"""
    if os.path.exists(DOWNLOADS_DIR):
        try:
            for filename in os.listdir(DOWNLOADS_DIR):
                file_path = os.path.join(DOWNLOADS_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.debug(f"Не удалось удалить {file_path}: {e}")
            logger.info("Папка downloads очищена")
        except Exception as e:
            logger.error(f"Ошибка при очистке downloads: {e}")

def validate_api_credentials(api_id, api_hash):
    if not api_id.isdigit():
        return "API ID должен состоять только из цифр"
    if len(api_hash) < 10:
        return "API HASH слишком короткий (проверьте данные с my.telegram.org)"
    return None

def validate_phone(phone):
    if not re.match(r'^\+\d{7,15}$', phone):
        return "Неверный формат номера. Используйте международный формат, например +79991234567"
    return None

def validate_code(code):
    if not code.isdigit():
        return "Код должен состоять только из цифр"
    if len(code) < 4:
        return "Код слишком короткий (обычно 5 цифр)"
    return None

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
    """Создает и возвращает клиент Pyrogram"""
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    session_password = os.environ.get("SESSION_PASSWORD")
    
    if not api_id or not api_hash:
        return None
        
    try:
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
        if "AUTH_KEY_UNREGISTERED" in str(e):
            logger.warning("Session unregistered. Deleting session file...")
            if os.path.exists("user_session.session"):
                try: os.remove("user_session.session")
                except: pass
        
        auth_session["step"] = "config"
        auth_session["error"] = f"Ошибка сессии: {str(e)}. Пожалуйста, настройте заново."
        await open_auth_page()
        return False
    finally:
        if client and client.is_connected:
            await client.disconnect()

async def open_auth_page():
    """Открывает страницу авторизации в браузере"""
    global web_app_runner, web_server_port, config_update_future
    if not web_app_runner: base_url = await start_web_server()
    else: base_url = f"http://127.0.0.1:{web_server_port}"
    webbrowser.open(f"{base_url}/auth")
    if not config_update_future or config_update_future.done():
        config_update_future = asyncio.Future()

async def handle_auth_get(request):
    """Отображает страницу авторизации"""
    step = auth_session["step"]
    error_msg = f'<p style="color: #ff4d4d; background: rgba(255,0,0,0.1); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,77,77,0.3); font-size: 14px; margin-bottom: 20px;">{auth_session["error"]}</p>' if auth_session["error"] else ""
    
    content = ""
    if step == "config":
        content = """
            <h2>1. Настройка API</h2>
            <p style="font-size: 14px; color: #94a3b8; margin-bottom: 20px;">Получите данные на <a href="https://my.telegram.org/apps" target="_blank" style="color: #38bdf8;">my.telegram.org</a></p>
            <form action="/auth/config" method="post">
                <div class="form-group"><label>API ID</label><input type="text" name="api_id" placeholder="1234567" required></div>
                <div class="form-group"><label>API HASH</label><input type="text" name="api_hash" placeholder="abc123def..." required></div>
                <button type="submit" class="btn">Сохранить</button>
            </form>
        """
    elif step == "phone":
        content = """
            <h2>2. Номер телефона</h2>
            <p style="font-size: 14px; color: #94a3b8; margin-bottom: 20px;">Введите номер в международном формате</p>
            <form action="/auth/phone" method="post" id="form"><div class="form-group"><label>Телефон</label><input type="text" name="phone" placeholder="+79501234567" required autofocus></div><button type="submit" class="btn" id="btn">Отправить код</button></form>
            <script>document.getElementById('form').onsubmit=()=>{{document.getElementById('btn').disabled=true;document.getElementById('btn').innerText='Отправка...'}}</script>
        """
    elif step == "code":
        content = """
            <h2>3. Код из Telegram</h2>
            <p style="font-size: 14px; color: #94a3b8; margin-bottom: 20px;">Код отправлен в ваше приложение Telegram</p>
            <form action="/auth/code" method="post" id="form"><div class="form-group"><label>Код</label><input type="text" name="code" placeholder="12345" required autofocus></div><button type="submit" class="btn" id="btn">Войти</button></form>
            <script>document.getElementById('form').onsubmit=()=>{{document.getElementById('btn').disabled=true;document.getElementById('btn').innerText='Проверка...'}}</script>
        """
    elif step == "password":
        content = """
            <h2>4. Облачный пароль (2FA)</h2>
            <p style="font-size: 14px; color: #94a3b8; margin-bottom: 20px;">Введите пароль двухфакторной аутентификации</p>
            <form action="/auth/password" method="post" id="form"><div class="form-group"><label>Пароль</label><input type="password" name="password" required autofocus></div><button type="submit" class="btn" id="btn">Подтвердить</button></form>
            <script>document.getElementById('form').onsubmit=()=>{{document.getElementById('btn').disabled=true;document.getElementById('btn').innerText='Вход...'}}</script>
        """
    else:
        content = """<div style="text-align: center;"><h2>✅ Готово!</h2><p>Авторизация прошла успешно. Эту вкладку можно закрыть.</p><button onclick="window.close()" class="btn" style="background: #334155; margin-top: 20px;">Закрыть</button></div>"""

    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"><title>Auth - Emoji MCP</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; background-color: #0f172a; color: white; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
        .container {{ background: #1e293b; padding: 40px; border-radius: 16px; width: 100%; max-width: 400px; border: 1px solid #334155; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }}
        h2 {{ margin: 0 0 10px 0; color: #38bdf8; font-size: 24px; }}
        .form-group {{ margin-bottom: 20px; }}
        label {{ display: block; margin-bottom: 8px; color: #94a3b8; font-size: 14px; }}
        input {{ width: 100%; padding: 12px; background: #0f172a; border: 1px solid #334155; border-radius: 8px; color: white; box-sizing: border-box; font-size: 16px; }}
        input:focus {{ outline: none; border-color: #38bdf8; }}
        .btn {{ background: #0284c7; color: white; border: none; padding: 14px; width: 100%; border-radius: 8px; cursor: pointer; font-weight: 600; transition: 0.2s; }}
        .btn:hover {{ background: #0369a1; }}
        .btn:disabled {{ background: #334155; opacity: 0.6; }}
        a {{ color: #38bdf8; text-decoration: none; }}
    </style></head><body><div class="container">{error_msg}{content}</div></body></html>
    """
    return web.Response(text=html, content_type='text/html')

async def handle_auth_config(request):
    data = await request.post()
    api_id = str(data.get('api_id', '')).strip()
    api_hash = str(data.get('api_hash', '')).strip()
    err = validate_api_credentials(api_id, api_hash)
    if err: auth_session["error"] = err
    else:
        set_key(ENV_FILE, "TG_API_ID", api_id)
        set_key(ENV_FILE, "TG_API_HASH", api_hash)
        os.environ["TG_API_ID"], os.environ["TG_API_HASH"] = api_id, api_hash
        auth_session["step"], auth_session["error"] = "phone", None
        if auth_session["client"]:
            try: await auth_session["client"].disconnect()
            except: pass
        auth_session["client"] = get_tg_client()
    return web.HTTPFound('/auth')

async def handle_auth_phone(request):
    data = await request.post()
    phone = str(data.get('phone', '')).strip()
    phone = re.sub(r'[^\d+]', '', phone)
    if not phone.startswith('+'):
        if len(phone) == 10 and phone.startswith('9'): phone = '+7' + phone
        else: phone = '+' + phone
    err = validate_phone(phone)
    if err: auth_session["error"] = err
    else:
        auth_session["phone"] = phone
        client = auth_session["client"] or get_tg_client()
        auth_session["client"] = client
        try:
            if not client.is_connected: await client.connect()
            code_obj = await client.send_code(phone)
            auth_session["phone_code_hash"] = code_obj.phone_code_hash
            auth_session["step"], auth_session["error"] = "code", None
        except pyrogram.errors.FloodWait as e: auth_session["error"] = f"Лимит запросов. Подождите {e.value} сек."
        except Exception as e: auth_session["error"] = f"Ошибка: {str(e)}"
    return web.HTTPFound('/auth')

async def handle_auth_code(request):
    data = await request.post()
    code = str(data.get('code', '')).strip()
    err = validate_code(code)
    if err: auth_session["error"] = err
    else:
        client = auth_session["client"]
        try:
            if not client.is_connected: await client.connect()
            await client.sign_in(auth_session["phone"], auth_session["phone_code_hash"], code)
            auth_session["step"], auth_session["error"] = "done", None
            if config_update_future and not config_update_future.done(): config_update_future.set_result(True)
            await client.disconnect()
        except pyrogram.errors.SessionPasswordNeeded: auth_session["step"], auth_session["error"] = "password", None
        except pyrogram.errors.PhoneCodeInvalid: auth_session["error"] = "Неверный код."
        except pyrogram.errors.PhoneCodeExpired: auth_session["error"] = "Код истек."; auth_session["step"] = "phone"
        except Exception as e: auth_session["error"] = f"Ошибка: {str(e)}"
    return web.HTTPFound('/auth')

async def handle_auth_password(request):
    data = await request.post()
    password = str(data.get('password', '')).strip()
    if not password: auth_session["error"] = "Введите пароль"
    else:
        client = auth_session["client"]
        try:
            if not client.is_connected: await client.connect()
            await client.check_password(password)
            auth_session["step"], auth_session["error"] = "done", None
            if config_update_future and not config_update_future.done(): config_update_future.set_result(True)
            await client.disconnect()
        except pyrogram.errors.PasswordHashInvalid: auth_session["error"] = "Неверный пароль."
        except Exception as e: auth_session["error"] = f"Ошибка: {str(e)}"
    return web.HTTPFound('/auth')

# --- Логика инструментов ---

def generate_html_viewer(downloaded_files, output_path="downloads/index.html"):
    grouped = {}
    for item in downloaded_files:
        base = item.get('base_emoji', 'Other')
        if base not in grouped: grouped[base] = []
        grouped[base].append(item)

    html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Emoji Selector</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js"></script>
    <style>
        body { font-family: sans-serif; background: #1e1e1e; color: white; padding: 20px; }
        .grid { display: flex; flex-wrap: wrap; gap: 15px; }
        .card { background: #2d2d2d; padding: 15px; border-radius: 10px; width: 180px; text-align: center; cursor: pointer; border: 2px solid transparent; position: relative; }
        .card:hover { border-color: #4da6ff; }
        .card.selected { border-color: #4da6ff; background: #3d3d3d; }
        .emoji-container { height: 80px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px; }
        video, img { max-width: 80px; max-height: 80px; }
        .info { font-size: 11px; color: #888; overflow: hidden; text-overflow: ellipsis; }
        .header { display: flex; justify-content: space-between; position: sticky; top: 0; background: #1e1e1e; padding: 10px 0; z-index: 10; border-bottom: 1px solid #333; }
        .btn { background: #4da6ff; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; }
    </style></head><body>
    <div class="header"><div><h2>Выберите эмодзи</h2></div><button id="btn" class="btn" onclick="submit()">Подтвердить</button></div>
    """
    for base, items in grouped.items():
        html += f"<h3>{base}</h3><div class='grid'>"
        for item in items:
            if not item['local_file_path']: continue
            fname = os.path.basename(item['local_file_path'])
            ext = os.path.splitext(fname)[1]
            html += f"<div class='card' id='c_{item['id']}' onclick='toggle(\"{item['id']}\")'><input type='checkbox' style='display:none' id='i_{item['id']}' data-id='{item['id']}' data-base='{base}'>"
            if ext == '.tgs':
                with gzip.open(item['local_file_path'], 'rt', encoding='utf-8') as f: data = f.read()
                html += f"<div class='emoji-container' id='l_{item['id']}'></div><script>lottie.loadAnimation({{container:document.getElementById('l_{item['id']}'),renderer:'svg',loop:true,autoplay:true,animationData:{data}}});</script>"
            elif ext == '.webm': html += f"<div class='emoji-container'><video autoplay loop muted src='{fname}'></video></div>"
            else: html += f"<div class='emoji-container'><img src='{fname}'></div>"
            html += f"<div class='info'>{item['pack_name']}</div></div>"
        html += "</div>"
    
    html += """<script>
        function toggle(id){ const c=document.getElementById('c_'+id),i=document.getElementById('i_'+id); i.checked=!i.checked; c.classList.toggle('selected',i.checked); }
        async function submit(){
            const s=[], btn=document.getElementById('btn');
            document.querySelectorAll('input:checked').forEach(i=>s.push({id:i.dataset.id, base_emoji:i.dataset.base}));
            if(!s.length) return alert('Выберите хотя бы один!');
            btn.disabled=true; btn.innerText='Отправка...';
            try { await fetch('/select',{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({selections:s})}); window.close(); } catch(e){ alert('Готово! Закройте вкладку.'); }
        }
    </script></body></html>"""
    with open(output_path, "w", encoding="utf-8") as f: f.write(html)
    return os.path.abspath(output_path)

async def handle_selection(request):
    global selected_emoji_future
    data = await request.json()
    if selected_emoji_future and not selected_emoji_future.done(): selected_emoji_future.set_result(data)
    return web.Response(text="OK", headers={'Access-Control-Allow-Origin': '*'})

async def start_web_server():
    global web_app_runner, web_server_port
    app = web.Application()
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    app.router.add_static('/static', path=DOWNLOADS_DIR, name='static')
    app.router.add_post('/select', handle_selection)
    app.router.add_get('/auth', handle_auth_get); app.router.add_post('/auth/config', handle_auth_config)
    app.router.add_post('/auth/phone', handle_auth_phone); app.router.add_post('/auth/code', handle_auth_code)
    app.router.add_post('/auth/password', handle_auth_password)
    app.router.add_get('/', lambda r: web.HTTPFound('/static/index.html'))
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    web_server_port = site._server.sockets[0].getsockname()[1]; web_app_runner = runner
    return f"http://127.0.0.1:{web_server_port}"

@mcp.tool()
async def search_and_select_emoji(emoticons: list[str], limit: int = 10, pack_name: str = None, is_animated: bool = None) -> dict:
    """Поиск кастомных эмодзи с выбором в браузере."""
    global selected_emoji_future, config_update_future
    if not emoticons: return {"error": "Список пуст"}
    limit = max(1, min(limit, 50))
    await check_for_updates()
    if not await ensure_authorized():
        try: await asyncio.wait_for(config_update_future, timeout=600.0)
        except asyncio.TimeoutError: return {"error": "Таймаут авторизации"}
    
    app = get_tg_client()
    async with app:
        try:
            ids = []
            for em in emoticons:
                res = await app.invoke(SearchCustomEmoji(emoticon=em, hash=0))
                if isinstance(res, EmojiList) and res.document_id: ids.extend(res.document_id[:limit])
            if not ids: return {"error": "Ничего не найдено"}
            
            docs = await app.invoke(GetCustomEmojiDocuments(document_id=list(set(ids))))
            details = []
            for doc in docs:
                alt, p_name = "", ""
                for a in doc.attributes:
                    if hasattr(a, 'alt'): alt = a.alt
                    if hasattr(a, 'stickerset'):
                        try:
                            s = await app.invoke(pyrogram.raw.functions.messages.GetStickerSet(stickerset=a.stickerset, hash=0))
                            p_name = s.set.short_name
                        except: pass
                mime = getattr(doc, 'mime_type', '')
                is_anim = mime in ('video/webm', 'application/x-tgsticker')
                if pack_name and pack_name.lower() not in p_name.lower(): continue
                if is_animated is not None and is_animated != is_anim: continue
                
                path = ""
                try:
                    ext = ".webm" if mime == 'video/webm' else (".tgs" if mime == 'application/x-tgsticker' else ".webp")
                    f_id = FileId(file_type=FileType.STICKER, dc_id=doc.dc_id, media_id=doc.id, access_hash=doc.access_hash, file_reference=doc.file_reference)
                    df = await app.download_media(f_id.encode(), file_name=f"emoji_{doc.id}{ext}")
                    if df: path = os.path.abspath(df)
                except Exception as e: logger.error(f"Err {doc.id}: {e}")
                details.append({"id": str(doc.id), "base_emoji": alt, "pack_name": p_name, "is_animated": is_anim, "local_file_path": path})
            
            if not details: return {"error": "Нет эмодзи после фильтров"}
            generate_html_viewer(details)
            base = f"http://127.0.0.1:{web_server_port}" if web_app_runner else await start_web_server()
            webbrowser.open(f"{base}/static/index.html")
            selected_emoji_future = asyncio.Future()
            try:
                sel = await asyncio.wait_for(selected_emoji_future, timeout=300.0)
                return {"status": "success", "selected_emojis": sel.get("selections", [])}
            except asyncio.TimeoutError: return {"error": "Таймаут выбора"}
        except Exception as e: return {"error": str(e)}

@mcp.tool()
async def search_emoji_auto(emoticons: list[str], limit: int = 5, pack_name: str = None, is_animated: bool = None) -> dict:
    """Автоматический поиск без участия пользователя."""
    global config_update_future
    if not emoticons: return {"error": "Список пуст"}
    await check_for_updates()
    if not await ensure_authorized():
        try: await asyncio.wait_for(config_update_future, timeout=600.0)
        except asyncio.TimeoutError: return {"error": "Таймаут"}
    app = get_tg_client()
    async with app:
        try:
            ids = []
            for em in emoticons:
                res = await app.invoke(SearchCustomEmoji(emoticon=em, hash=0))
                if isinstance(res, EmojiList) and res.document_id: ids.extend(res.document_id[:limit])
            if not ids: return {"error": "Ничего не найдено"}
            docs = await app.invoke(GetCustomEmojiDocuments(document_id=list(set(ids))))
            res = []
            for doc in docs:
                alt, p_name = "", ""
                for a in doc.attributes:
                    if hasattr(a, 'alt'): alt = a.alt
                    if hasattr(a, 'stickerset'):
                        try:
                            s = await app.invoke(pyrogram.raw.functions.messages.GetStickerSet(stickerset=a.stickerset, hash=0))
                            p_name = s.set.short_name
                        except: pass
                mime = getattr(doc, 'mime_type', '')
                is_anim = mime in ('video/webm', 'application/x-tgsticker')
                if pack_name and pack_name.lower() not in p_name.lower(): continue
                if is_animated is not None and is_animated != is_anim: continue
                res.append({"id": str(doc.id), "base_emoji": alt, "pack_name": p_name, "is_animated": is_anim})
            return {"status": "success", "results": res}
        except Exception as e: return {"error": str(e)}

def main():
    cleanup_downloads()
    mcp.run()

if __name__ == "__main__":
    main()
