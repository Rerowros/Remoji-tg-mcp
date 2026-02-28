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
VERSION = "0.1.8"
PACKAGE_NAME = "remoji-tg-mcp"

# Принудительная установка UTF-8 для вывода в консоль (Windows fix)
if sys.platform == "win32":
    import io
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

logger = logging.getLogger("tg-emoji-mcp")

# Загружаем .env
load_dotenv()

# Инициализация MCP
mcp = FastMCP("TelegramEmojiSearch")

# Пути
BASE_DIR = os.path.abspath(os.getcwd())
ENV_FILE = os.path.join(BASE_DIR, ".env")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

# Глобальные переменные
selected_emoji_future = None
config_update_future = None
web_app_runner = None
web_server_port = None

auth_session = {
    "client": None, "phone": None, "phone_code_hash": None,
    "step": "config", "error": None
}

# --- Утилиты ---

def cleanup_downloads():
    """Полная очистка папки загрузок"""
    if os.path.exists(DOWNLOADS_DIR):
        try:
            for filename in os.listdir(DOWNLOADS_DIR):
                file_path = os.path.join(DOWNLOADS_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path): os.unlink(file_path)
                    elif os.path.isdir(file_path): shutil.rmtree(file_path)
                except Exception: pass
            logger.info("Папка downloads очищена")
        except Exception as e:
            logger.error(f"Ошибка очистки: {e}")

def get_tg_client():
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    session_password = os.environ.get("SESSION_PASSWORD")
    if not api_id or not api_hash: return None
    try:
        return Client(
            os.path.join(BASE_DIR, "user_session"), 
            api_id=int(api_id), api_hash=api_hash, 
            password=session_password, device_model="MCP Server"
        )
    except: return None

async def check_for_updates():
    try:
        async with ClientSession() as session:
            async with session.get(f"https://pypi.org/pypi/{PACKAGE_NAME}/json", timeout=5) as r:
                if r.status == 200:
                    data = await r.json()
                    latest = data["info"]["version"]
                    if latest != VERSION:
                        logger.warning(f"\n!!! ДОСТУПНО ОБНОВЛЕНИЕ: {latest} (у вас {VERSION}) !!!\nКоманда: uv tool upgrade {PACKAGE_NAME}\n")
    except: pass

async def ensure_authorized():
    global config_update_future, auth_session
    client = get_tg_client()
    if not client:
        auth_session["step"] = "config"
        await open_auth_page(); return False
    try:
        await client.connect()
        if await client.get_me(): await client.disconnect(); return True
        else: auth_session["step"] = "phone"; auth_session["client"] = client; await open_auth_page(); return False
    except Exception as e:
        if "AUTH_KEY_UNREGISTERED" in str(e):
            sess_path = os.path.join(BASE_DIR, "user_session.session")
            if os.path.exists(sess_path): os.remove(sess_path)
        auth_session["step"], auth_session["error"] = "config", f"Ошибка: {e}"
        await open_auth_page(); return False
    finally:
        if client and client.is_connected: await client.disconnect()

async def open_auth_page():
    global web_app_runner, web_server_port, config_update_future
    base = f"http://127.0.0.1:{web_server_port}" if web_app_runner else await start_web_server()
    webbrowser.open(f"{base}/auth")
    if not config_update_future or config_update_future.done(): config_update_future = asyncio.Future()

# --- Web Handlers ---

async def handle_auth_get(request):
    step, err = auth_session["step"], auth_session["error"]
    error_html = f'<p style="color:#ff4d4d;background:rgba(255,0,0,0.1);padding:12px;border-radius:8px;margin-bottom:20px;">{err}</p>' if err else ""
    content = ""
    if step == "config":
        content = """<h2>1. API Настройка</h2><form action="/auth/config" method="post"><div class="form-group"><label>API ID</label><input type="text" name="api_id" required></div><div class="form-group"><label>API HASH</label><input type="text" name="api_hash" required></div><button type="submit" class="btn">Далее</button></form>"""
    elif step == "phone":
        content = """<h2>2. Телефон</h2><form action="/auth/phone" method="post" id="f"><div class="form-group"><label>Номер</label><input type="text" name="phone" placeholder="+7..." required autofocus></div><button type="submit" class="btn" id="b">Код</button></form><script>document.getElementById('f').onsubmit=()=>{{document.getElementById('b').disabled=true}}</script>"""
    elif step == "code":
        content = """<h2>3. Код</h2><form action="/auth/code" method="post" id="f"><div class="form-group"><label>Код из Telegram</label><input type="text" name="code" required autofocus></div><button type="submit" class="btn" id="b">Войти</button></form><script>document.getElementById('f').onsubmit=()=>{{document.getElementById('b').disabled=true}}</script>"""
    elif step == "password":
        content = """<h2>4. Пароль (2FA)</h2><form action="/auth/password" method="post" id="f"><div class="form-group"><label>Пароль</label><input type="password" name="password" required autofocus></div><button type="submit" class="btn" id="b">Войти</button></form><script>document.getElementById('f').onsubmit=()=>{{document.getElementById('b').disabled=true}}</script>"""
    else:
        content = "<h2>✅ Авторизовано!</h2><p>Эту вкладку можно закрыть.</p>"

    return web.Response(text=f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Auth</title><style>body{{font-family:sans-serif;background:#0f172a;color:white;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}.container{{background:#1e293b;padding:40px;border-radius:16px;width:320px;border:1px solid #334155}}.form-group{{margin-bottom:15px}}label{{display:block;margin-bottom:5px;color:#94a3b8;font-size:14px}}input{{width:100%;padding:10px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white;box-sizing:border-box}}.btn{{width:100%;background:#0284c7;color:white;border:none;padding:12px;border-radius:8px;cursor:pointer;font-weight:600}}</style></head><body><div class="container">{error_html}{content}</div></body></html>""", content_type='text/html')

async def handle_auth_config(request):
    d = await request.post(); aid, ah = str(d.get('api_id','')).strip(), str(d.get('api_hash','')).strip()
    if aid.isdigit() and len(ah)>10:
        set_key(ENV_FILE, "TG_API_ID", aid); set_key(ENV_FILE, "TG_API_HASH", ah)
        os.environ["TG_API_ID"], os.environ["TG_API_HASH"] = aid, ah
        auth_session["step"], auth_session["error"] = "phone", None
        if auth_session["client"]: 
            try: await auth_session["client"].disconnect()
            except: pass
        auth_session["client"] = get_tg_client()
    else: auth_session["error"] = "Неверные данные API"
    return web.HTTPFound('/auth')

async def handle_auth_phone(request):
    d = await request.post(); p = str(d.get('phone','')).strip()
    p = re.sub(r'[^\d+]', '', p)
    if not p.startswith('+'): p = ('+7' if len(p)==10 and p.startswith('9') else '+') + p
    auth_session["phone"] = p
    c = auth_session["client"] or get_tg_client(); auth_session["client"] = c
    try:
        if not c.is_connected: await c.connect()
        res = await c.send_code(p); auth_session["phone_code_hash"] = res.phone_code_hash
        auth_session["step"], auth_session["error"] = "code", None
    except Exception as e: auth_session["error"] = str(e)
    return web.HTTPFound('/auth')

async def handle_auth_code(request):
    d = await request.post(); code = str(d.get('code','')).strip()
    c = auth_session["client"]
    try:
        if not c.is_connected: await c.connect()
        await c.sign_in(auth_session["phone"], auth_session["phone_code_hash"], code)
        auth_session["step"], auth_session["error"] = "done", None
        if config_update_future and not config_update_future.done(): config_update_future.set_result(True)
        await c.disconnect()
    except pyrogram.errors.SessionPasswordNeeded: auth_session["step"], auth_session["error"] = "password", None
    except Exception as e: auth_session["error"] = str(e)
    return web.HTTPFound('/auth')

async def handle_auth_password(request):
    d = await request.post(); pw = str(d.get('password','')).strip()
    c = auth_session["client"]
    try:
        if not c.is_connected: await c.connect()
        await c.check_password(pw)
        auth_session["step"], auth_session["error"] = "done", None
        if config_update_future and not config_update_future.done(): config_update_future.set_result(True)
        await c.disconnect()
    except Exception as e: auth_session["error"] = str(e)
    return web.HTTPFound('/auth')

# --- Инструменты ---

def generate_html_viewer(files):
    grouped = {}
    for f in files:
        b = f.get('base_emoji', 'Other')
        if b not in grouped: grouped[b] = []
        grouped[b].append(f)
    
    items_html = ""
    for base, items in grouped.items():
        items_html += f"<h3>{base}</h3><div style='display:flex;flex-wrap:wrap;gap:10px;'>"
        for i in items:
            if not i['local_file_path']: continue
            fn = os.path.basename(i['local_file_path'])
            ext = os.path.splitext(fn)[1]
            media = f"<video autoplay loop muted src='{fn}' style='width:64px'></video>" if ext=='.webm' else (f"<img src='{fn}' style='width:64px'>" if ext!='.tgs' else f"<div id='l_{i['id']}' style='width:64px;height:64px'></div><script>lottie.loadAnimation({{container:document.getElementById('l_{i['id']}'),renderer:'svg',loop:true,autoplay:true,animationData:{gzip.open(i['local_file_path'],'rt').read()}}})</script>")
            items_html += f"<div id='c_{i['id']}' onclick='t(\"{i['id']}\")' style='background:#2d2d2d;padding:10px;border-radius:8px;cursor:pointer;border:2px solid transparent'><input type='checkbox' style='display:none' id='i_{i['id']}' data-id='{i['id']}' data-base='{base}'>{media}</div>"
        items_html += "</div>"

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><script src="https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js"></script><style>body{{font-family:sans-serif;background:#1e1e1e;color:white;padding:20px}}.selected{{border-color:#4da6ff !important;background:#3d3d3d !important}}.header{{display:flex;justify-content:space-between;position:sticky;top:0;background:#1e1e1e;padding:10px 0;z-index:10;border-bottom:1px solid #333}}</style></head><body><div class="header"><h2>Выбор Эмодзи</h2><button onclick="s()" style="background:#4da6ff;color:white;border:none;padding:10px 20px;border-radius:5px;cursor:pointer;font-weight:bold">Готово</button></div>{items_html}<script>function t(id){{const c=document.getElementById('c_'+id),i=document.getElementById('i_'+id);i.checked=!i.checked;c.classList.toggle('selected',i.checked)}}async function s(){{const res=[];document.querySelectorAll('input:checked').forEach(i=>res.push({{id:i.dataset.id,base_emoji:i.dataset.base}}));if(!res.length)return alert('Выберите!');try{{await fetch('/select',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{selections:res}})}});window.close()}}catch(e){{alert('Ошибка, но выбор зафиксирован')}}}}</script></body></html>"""
    with open(os.path.join(DOWNLOADS_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(html)

async def start_web_server():
    global web_app_runner, web_server_port
    app = web.Application(); os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    app.router.add_static('/static', path=DOWNLOADS_DIR, name='static')
    app.router.add_post('/select', lambda r: (selected_emoji_future.set_result(asyncio.create_task(r.json())) if not selected_emoji_future.done() else None, web.Response(text="OK"))[1])
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
    """Поиск эмодзи с интерактивным выбором в браузере."""
    global selected_emoji_future
    cleanup_downloads()
    await check_for_updates()
    if not await ensure_authorized():
        try: await asyncio.wait_for(config_update_future, 600.0)
        except: return {"error": "Таймаут авторизации"}
    
    app = get_tg_client()
    async with app:
        try:
            ids = []
            for em in emoticons:
                res = await app.invoke(SearchCustomEmoji(emoticon=em, hash=0))
                if isinstance(res, EmojiList) and res.document_id: ids.extend(res.document_id[:limit])
            if not ids: return {"error": "Не найдено"}
            
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
                ext = ".webm" if mime == 'video/webm' else (".tgs" if mime == 'application/x-tgsticker' else ".webp")
                df = await app.download_media(FileId(file_type=FileType.STICKER, dc_id=doc.dc_id, media_id=doc.id, access_hash=doc.access_hash, file_reference=doc.file_reference).encode(), file_name=f"emoji_{doc.id}{ext}")
                details.append({"id": str(doc.id), "base_emoji": alt, "pack_name": p_name, "is_animated": is_anim, "local_file_path": os.path.abspath(df) if df else ""})
            
            if not details: return {"error": "Нет эмодзи после фильтров"}
            generate_html_viewer(details)
            base = f"http://127.0.0.1:{web_server_port}" if web_app_runner else await start_web_server()
            webbrowser.open(f"{base}/static/index.html")
            selected_emoji_future = asyncio.Future()
            try:
                sel_task = await asyncio.wait_for(selected_emoji_future, 300.0)
                sel = await sel_task
                await asyncio.sleep(0.5)
                cleanup_downloads() # Очистка СРАЗУ после выбора
                return {"status": "success", "selected_emojis": sel.get("selections", [])}
            except: return {"error": "Таймаут"}
        except Exception as e: return {"error": str(e)}

@mcp.tool()
async def search_emoji_auto(emoticons: list[str], limit: int = 5, pack_name: str = None, is_animated: bool = None) -> dict:
    """Прямой поиск без выбора."""
    await check_for_updates()
    if not await ensure_authorized(): return {"error": "Нужна авторизация"}
    app = get_tg_client()
    async with app:
        try:
            ids = []
            for em in emoticons:
                res = await app.invoke(SearchCustomEmoji(emoticon=em, hash=0))
                if isinstance(res, EmojiList) and res.document_id: ids.extend(res.document_id[:limit])
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
    logger.info(f"Запуск Remoji TG MCP v{VERSION}")
    logger.info(f"Данные хранятся в: {BASE_DIR}")
    cleanup_downloads()
    mcp.run()

if __name__ == "__main__": main()
