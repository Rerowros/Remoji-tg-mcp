# /// script
# dependencies = [
#   "mcp",
#   "pyrogram",
#   "tgcrypto",
#   "platformdirs",
#   "python-dotenv",
#   "aiohttp"
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
from platformdirs import user_data_dir

# Version 0.3.1 - Enhanced AI Prompts (No text names for emojis)
VERSION = "0.3.1"
PACKAGE_NAME = "remoji-tg-mcp"

# --- Paths ---
BASE_DIR = user_data_dir(PACKAGE_NAME, "Rerowros")
os.makedirs(BASE_DIR, exist_ok=True)
ENV_FILE = os.path.join(BASE_DIR, ".env")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
SESSION_FILE = os.path.join(BASE_DIR, "user_session")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# --- Encoding Fix ---
if sys.platform == "win32":
    try:
        if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8')
        if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

# --- Logging ---
logger = logging.getLogger("tg-emoji-mcp")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
for l in ["pyrogram", "asyncio", "aiohttp"]: logging.getLogger(l).setLevel(logging.WARNING)

load_dotenv(ENV_FILE)
mcp = FastMCP("TelegramEmojiSearch")

selected_emoji_future = None
config_update_future = None
web_app_runner = None
web_server_port = None
_update_checked = False

auth_session = {
    "client": None, "phone": None, "phone_code_hash": None,
    "step": "config", "error": None
}

# --- Utils ---

def cleanup_downloads():
    if os.path.exists(DOWNLOADS_DIR):
        try:
            for f in os.listdir(DOWNLOADS_DIR):
                path = os.path.join(DOWNLOADS_DIR, f)
                if os.path.isfile(path): os.unlink(path)
                elif os.path.isdir(path): shutil.rmtree(path)
            logger.info("Downloads cleared")
        except Exception as e: logger.error(f"Cleanup error: {e}")

def get_tg_client():
    api_id, api_hash = os.environ.get("TG_API_ID"), os.environ.get("TG_API_HASH")
    pw = os.environ.get("SESSION_PASSWORD")
    if not api_id or not api_hash: return None
    return Client(SESSION_FILE, api_id=int(api_id), api_hash=api_hash, password=pw, device_model="MCP Server")

async def check_for_updates():
    global _update_checked
    if _update_checked: return
    _update_checked = True
    try:
        async with ClientSession() as s:
            async with s.get(f"https://pypi.org/pypi/{PACKAGE_NAME}/json", timeout=3) as r:
                if r.status == 200:
                    latest = (await r.json())["info"]["version"]
                    if latest != VERSION:
                        logger.warning(f"\n{'!'*50}\nUPDATE AVAILABLE: {latest} (current {VERSION})\nRun: uvx --refresh {PACKAGE_NAME}\n{'!'*50}")
    except: pass

async def ensure_authorized():
    global auth_session, config_update_future
    client = get_tg_client()
    if not client:
        auth_session["step"] = "config"
        await open_auth_page(); return False
    try:
        await client.connect()
        if await client.get_me(): await client.disconnect(); return True
        auth_session.update({"step": "phone", "client": client})
        await open_auth_page(); return False
    except Exception as e:
        if any(x in str(e) for x in ["AUTH_KEY_UNREGISTERED", "SESSION_REVOKED", "SESSION_EXPIRED"]):
            for ext in [".session", ".session-journal"]:
                path = SESSION_FILE + ext
                if os.path.exists(path): os.remove(path)
        auth_session.update({"step": "config", "error": str(e)})
        await open_auth_page(); return False
    finally:
        if client and client.is_connected: await client.disconnect()

async def open_auth_page():
    global web_app_runner, web_server_port, config_update_future
    url = f"http://127.0.0.1:{web_server_port}/auth" if web_app_runner else await start_web_server() + "/auth"
    webbrowser.open(url)
    if not config_update_future or config_update_future.done(): config_update_future = asyncio.Future()

async def wait_for_auth():
    global config_update_future
    logger.info("Waiting for authorization in browser...")
    try:
        await asyncio.wait_for(config_update_future, 600.0)
        return True
    except: return False

# --- Web ---

async def handle_auth_get(request):
    s, err = auth_session["step"], auth_session["error"]
    err_html = f'<div style="color:#ff4d4d;background:rgba(255,0,0,0.1);padding:15px;border-radius:10px;margin-bottom:20px;border:1px solid #ff4d4d">{err}</div>' if err else ""
    forms = {
        "config": '<h2>1. API Setup</h2><p style="color:#94a3b8;font-size:12px">Data stored in AppData</p><form action="/auth/config" method="post"><label>API ID</label><input type="text" name="api_id" required><label>API HASH</label><input type="text" name="api_hash" required><button class="btn">Save</button></form>',
        "phone": '<h2>2. Phone</h2><form action="/auth/phone" method="post"><label>Number</label><input type="text" name="phone" placeholder="+7..." required autofocus><button class="btn">Get Code</button></form>',
        "code": '<h2>3. Code</h2><form action="/auth/code" method="post"><label>Telegram Code</label><input type="text" name="code" required autofocus><button class="btn">Login</button></form>',
        "password": '<h2>4. 2FA Password</h2><form action="/auth/password" method="post"><label>Password</label><input type="password" name="password" required autofocus><button class="btn">Confirm</button></form>',
        "done": '<h2>✅ Authorized!</h2><p>You can close this tab now.</p>'
    }
    return web.Response(text=f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Auth</title><style>body{{font-family:sans-serif;background:#0f172a;color:white;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}.container{{background:#1e293b;padding:40px;border-radius:20px;width:350px;box-shadow:0 20px 50px rgba(0,0,0,0.5);border:1px solid #334155}}label{{display:block;margin:15px 0 5px;color:#94a3b8;font-size:14px}}input{{width:100%;padding:12px;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;box-sizing:border-box;font-size:16px}}.btn{{width:100%;background:#0284c7;color:white;border:none;padding:15px;border-radius:10px;margin-top:20px;cursor:pointer;font-weight:bold}}</style></head><body><div class="container">{err_html}{forms.get(s, forms["config"])}</div></body></html>', content_type='text/html')

async def handle_auth_config(request):
    d = await request.post(); aid, ah = str(d.get('api_id','')).strip(), str(d.get('api_hash','')).strip()
    if aid.isdigit() and len(ah)>10:
        set_key(ENV_FILE, "TG_API_ID", aid); set_key(ENV_FILE, "TG_API_HASH", ah); os.environ.update({"TG_API_ID": aid, "TG_API_HASH": ah})
        auth_session.update({"step": "phone", "error": None})
        if auth_session["client"]: await auth_session["client"].disconnect()
        auth_session["client"] = get_tg_client()
    else: auth_session["error"] = "Invalid API data"
    return web.HTTPFound('/auth')

async def handle_auth_phone(request):
    d = await request.post(); p = str(d.get('phone','')).strip()
    p = re.sub(r'[^\d+]', '', p)
    if not p.startswith('+'): p = ('+7' if len(p)==10 and p.startswith('9') else '+') + p
    c = auth_session["client"] or get_tg_client(); auth_session.update({"client": c, "phone": p})
    try:
        if not c.is_connected: await c.connect()
        res = await c.send_code(p); auth_session.update({"phone_code_hash": res.phone_code_hash, "step": "code", "error": None})
    except Exception as e: auth_session["error"] = str(e)
    return web.HTTPFound('/auth')

async def handle_auth_code(request):
    d = await request.post(); code = str(d.get('code','')).strip(); c = auth_session["client"]
    try:
        await c.sign_in(auth_session["phone"], auth_session["phone_code_hash"], code)
        auth_session.update({"step": "done", "error": None})
        if config_update_future and not config_update_future.done(): config_update_future.set_result(True)
        await c.disconnect()
    except pyrogram.errors.SessionPasswordNeeded: auth_session["step"] = "password"
    except Exception as e: auth_session["error"] = str(e)
    return web.HTTPFound('/auth')

async def handle_auth_password(request):
    d = await request.post(); pw = str(d.get('password','')).strip(); c = auth_session["client"]
    try:
        await c.check_password(pw); auth_session.update({"step": "done", "error": None})
        if config_update_future and not config_update_future.done(): config_update_future.set_result(True)
        await c.disconnect()
    except Exception as e: auth_session["error"] = str(e)
    return web.HTTPFound('/auth')

# --- MCP Tool Logic ---

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
async def search_and_select_emoji(
    emoticons: list[str], 
    limit: int = 10, 
    pack_name: str = None, 
    is_animated: bool = None
) -> dict:
    """
    Interactive tool to search for custom Telegram emojis. Opens a browser UI for selection.
    
    Args:
        emoticons: List of SINGLE Unicode emoji symbols (e.g. ["🔥", "💎"]). 
                   CRITICAL: DO NOT use text names like 'fire'. ONLY USE SYMBOLS.
        limit: Max results per symbol (max 50).
        pack_name: Optional filter by pack name.
        is_animated: Optional filter for animation.
    """
    global selected_emoji_future
    cleanup_downloads(); await check_for_updates()
    if not await ensure_authorized() and not await wait_for_auth(): return {"error": "Auth failed"}
    app = get_tg_client()
    async with app:
        try:
            ids = []
            for em in emoticons:
                try:
                    res = await app.invoke(SearchCustomEmoji(emoticon=em, hash=0))
                    if isinstance(res, EmojiList) and res.document_id: ids.extend(res.document_id[:limit])
                except pyrogram.errors.Unauthorized: await ensure_authorized(); await wait_for_auth()
            if not ids: return {"error": "No emojis found. Ensure you provided actual Unicode symbols, not text names."}
            docs = await app.invoke(GetCustomEmojiDocuments(document_id=list(set(ids))))
            details = []
            for d in docs:
                alt, p_name = "", ""
                for a in d.attributes:
                    if hasattr(a, 'alt'): alt = a.alt
                    if hasattr(a, 'stickerset'):
                        try:
                            s = await app.invoke(pyrogram.raw.functions.messages.GetStickerSet(stickerset=a.stickerset, hash=0))
                            p_name = s.set.short_name
                        except: pass
                mime = getattr(d, 'mime_type', '')
                is_anim = mime in ('video/webm', 'application/x-tgsticker')
                if (pack_name and pack_name.lower() not in p_name.lower()) or (is_animated is not None and is_animated != is_anim): continue
                ext = ".webm" if mime == 'video/webm' else (".tgs" if mime == 'application/x-tgsticker' else ".webp")
                df = await app.download_media(FileId(file_type=FileType.STICKER, dc_id=d.dc_id, media_id=d.id, access_hash=d.access_hash, file_reference=d.file_reference).encode(), file_name=os.path.join(DOWNLOADS_DIR, f"emoji_{d.id}{ext}"))
                details.append({"id": str(d.id), "base_emoji": alt, "pack_name": p_name, "is_animated": is_anim, "local_file_path": os.path.abspath(df)})
            if not details: return {"error": "No results after filtering"}
            
            h = ""
            for i in details:
                fn = os.path.basename(i['local_file_path']); ext = os.path.splitext(fn)[1]
                media = f"<video autoplay loop muted src='{fn}'></video>" if ext=='.webm' else (f"<img src='{fn}'>" if ext!='.tgs' else f"<div id='l_{i['id']}'></div><script>lottie.loadAnimation({{container:document.getElementById('l_{i['id']}'),renderer:'svg',loop:true,autoplay:true,animationData:{gzip.open(i['local_file_path'],'rt').read()}}})</script>")
                h += f"<div class='card' onclick='t(\"{i['id']}\")' id='c_{i['id']}'><input type='checkbox' style='display:none' id='i_{i['id']}' data-id='{i['id']}' data-base='{i['base_emoji']}'>{media}</div>"
            with open(os.path.join(DOWNLOADS_DIR, "index.html"), "w", encoding="utf-8") as f:
                f.write(f"<!DOCTYPE html><html><head><meta charset='utf-8'><script src='https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js'></script><style>body{{background:#1e1e1e;color:white;font-family:sans-serif;padding:20px}}.grid{{display:flex;flex-wrap:wrap;gap:10px}}.card{{background:#2d2d2d;padding:10px;border-radius:10px;cursor:pointer;border:2px solid transparent;width:80px;height:80px;display:flex;align-items:center;justify-content:center}}video,img,div{{max-width:60px;max-height:60px}}.selected{{border-color:#4da6ff;background:#3d3d3d}}.header{{display:flex;justify-content:space-between;margin-bottom:20px;position:sticky;top:0;background:#1e1e1e;padding:10px 0;border-bottom:1px solid #333}}.btn{{background:#4da6ff;color:white;border:none;padding:10px 20px;border-radius:5px;cursor:pointer;font-weight:bold}}</style></head><body><div class='header'><h2>Selection</h2><button onclick='s()' class='btn'>Done</button></div><div class='grid'>{h}</div><script>function t(id){{const c=document.getElementById('c_'+id),i=document.getElementById('i_'+id);i.checked=!i.checked;c.classList.toggle('selected',i.checked)}}async function s(){{const res=[];document.querySelectorAll('input:checked').forEach(i=>res.push({{id:i.dataset.id,base_emoji:i.dataset.base}}));if(!res.length)return alert('Select one!');await fetch('/select',{{method:'POST',body:JSON.stringify({{selections:res}})}});window.close()}}</script></body></html>")
            
            base = f"http://127.0.0.1:{web_server_port}" if web_app_runner else await start_web_server()
            webbrowser.open(f"{base}/static/index.html")
            selected_emoji_future = asyncio.Future()
            try:
                res = await (await asyncio.wait_for(selected_emoji_future, 300.0))
                cleanup_downloads(); return {"status": "success", "selected_emojis": res.get("selections", [])}
            except: return {"error": "Timeout"}
        except Exception as e: return {"error": str(e)}

@mcp.tool()
async def search_emoji_auto(
    emoticons: list[str], 
    limit: int = 5, 
    pack_name: str = None, 
    is_animated: bool = None
) -> dict:
    """
    Non-interactive search for Telegram emojis. Returns a raw list of metadata.
    
    Args:
        emoticons: List of SINGLE Unicode emoji symbols (e.g. ["🔥", "💎"]). 
                   CRITICAL: DO NOT use text names like 'fire'. ONLY USE SYMBOLS.
        limit: Max results per symbol.
        pack_name: Optional filter by pack name.
        is_animated: Optional filter for animation.
    """
    await check_for_updates()
    if not await ensure_authorized() and not await wait_for_auth(): return {"error": "Auth failed"}
    app = get_tg_client()
    async with app:
        try:
            ids = []
            for em in emoticons:
                try:
                    res = await app.invoke(SearchCustomEmoji(emoticon=em, hash=0))
                    if isinstance(res, EmojiList) and res.document_id: ids.extend(res.document_id[:limit])
                except pyrogram.errors.Unauthorized: await ensure_authorized(); await wait_for_auth()
            if not ids: return {"error": "No emojis found. Ensure you provided actual Unicode symbols."}
            docs = await app.invoke(GetCustomEmojiDocuments(document_id=list(set(ids))))
            results = []
            for d in docs:
                alt, p_name = "", ""
                for a in d.attributes:
                    if hasattr(a, 'alt'): alt = a.alt
                    if hasattr(a, 'stickerset'):
                        try:
                            s = await app.invoke(pyrogram.raw.functions.messages.GetStickerSet(stickerset=a.stickerset, hash=0))
                            p_name = s.set.short_name
                        except: pass
                mime = getattr(d, 'mime_type', '')
                is_anim = mime in ('video/webm', 'application/x-tgsticker')
                if (pack_name and pack_name.lower() not in p_name.lower()) or (is_animated is not None and is_animated != is_anim): continue
                results.append({"id": str(d.id), "base_emoji": alt, "pack_name": p_name, "is_animated": is_anim})
            return {"status": "success", "results": results}
        except Exception as e: return {"error": str(e)}

def main():
    logger.info(f"Remoji TG MCP v{VERSION}. Data path: {BASE_DIR}")
    cleanup_downloads(); mcp.run()

if __name__ == "__main__": main()
