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
from pyrogram.raw.functions.account import GetPassword
from pyrogram.raw.types import EmojiList
from pyrogram.file_id import FileId, FileType
from dotenv import load_dotenv, set_key
from platformdirs import user_data_dir

# Version 0.4.4 - High-speed parallel search and download
VERSION = "0.4.4"
PACKAGE_NAME = "remoji-tg-mcp"

# --- Paths ---
BASE_DIR = user_data_dir(PACKAGE_NAME, "Rerowros")
os.makedirs(BASE_DIR, exist_ok=True)
ENV_FILE = os.path.join(BASE_DIR, ".env")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
SESSION_FILE = os.path.join(BASE_DIR, "user_session")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# --- Encoding ---
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
    "step": "config", "error": None, "pwd_hint": None
}

# --- Utils ---

def cleanup_downloads():
    if os.path.exists(DOWNLOADS_DIR):
        for f in os.listdir(DOWNLOADS_DIR):
            try:
                p = os.path.join(DOWNLOADS_DIR, f)
                if os.path.isfile(p): os.unlink(p)
                elif os.path.isdir(p): shutil.rmtree(p)
            except: pass

def get_tg_client():
    api_id, api_hash = os.environ.get("TG_API_ID"), os.environ.get("TG_API_HASH")
    if not api_id or not api_hash: return None
    return Client(SESSION_FILE, api_id=int(api_id), api_hash=api_hash, password=os.environ.get("SESSION_PASSWORD"), device_model="MCP Server")

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
                        logger.info(f"Update available: {latest} (current {VERSION}). Run: uvx --refresh {PACKAGE_NAME}")
    except: pass

async def ensure_authorized():
    global auth_session, config_update_future
    client = get_tg_client()
    if not client: auth_session["step"] = "config"; await open_auth_page(); return False
    try:
        await client.connect()
        if await client.get_me(): await client.disconnect(); return True
        auth_session.update({"step": "phone", "client": client}); await open_auth_page(); return False
    except Exception as e:
        if "AUTH_KEY_UNREGISTERED" in str(e):
            for ext in [".session", ".session-journal"]:
                p = SESSION_FILE + ext
                if os.path.exists(p): os.remove(p)
        auth_session.update({"step": "config", "error": str(e)}); await open_auth_page(); return False
    finally:
        if client and client.is_connected: await client.disconnect()

async def open_auth_page():
    global web_app_runner, web_server_port, config_update_future
    url = f"http://127.0.0.1:{web_server_port}/auth" if web_app_runner else await start_web_server() + "/auth"
    webbrowser.open(url)
    if not config_update_future or config_update_future.done(): config_update_future = asyncio.Future()

async def wait_for_auth():
    global config_update_future
    try: await asyncio.wait_for(config_update_future, 600.0); return True
    except: return False

# --- Web ---

async def handle_auth_get(request):
    s, err, hint = auth_session["step"], auth_session["error"], auth_session["pwd_hint"]
    err_h = f'<div style="color:#ff4d4d;background:rgba(255,0,0,0.1);padding:15px;border-radius:10px;margin-bottom:20px;border:1px solid #ff4d4d">{err}</div>' if err else ""
    hint_h = f'<p style="color:#94a3b8;font-size:13px;margin-bottom:15px">Hint: {hint}</p>' if hint else ""
    forms = {
        "config": '<h2>1. API Setup</h2><form action="/auth/config" method="post"><label>API ID</label><input type="text" name="api_id" required><label>API HASH</label><input type="text" name="api_hash" required><button class="btn">Save</button></form>',
        "phone": '<h2>2. Phone</h2><form action="/auth/phone" method="post"><label>Number</label><input type="text" name="phone" placeholder="+7..." required autofocus><button class="btn">Get Code</button></form>',
        "code": '<h2>3. Code</h2><form action="/auth/code" method="post"><label>Code</label><input type="text" name="code" required autofocus><button class="btn">Login</button></form>',
        "password": f'<h2>4. Password</h2>{hint_h}<form action="/auth/password" method="post"><label>Password</label><input type="password" name="password" required autofocus><button class="btn">Confirm</button></form>',
        "done": '<h2>✅ Success!</h2><p>Authorized. Close this tab.</p>'
    }
    return web.Response(text=f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Auth</title><style>body{{font-family:sans-serif;background:#0f172a;color:white;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}.container{{background:#1e293b;padding:40px;border-radius:20px;width:350px;border:1px solid #334155}}label{{display:block;margin:15px 0 5px;color:#94a3b8;font-size:14px}}input{{width:100%;padding:12px;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;box-sizing:border-box;font-size:16px}}.btn{{width:100%;background:#0284c7;color:white;border:none;padding:15px;border-radius:10px;margin-top:20px;cursor:pointer;font-weight:bold}}</style></head><body><div class="container">{err_h}{forms.get(s, forms["config"])}</div></body></html>', content_type='text/html')

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
    d = await request.post(); p = re.sub(r'[^\d+]', '', str(d.get('phone','')).strip())
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
    except pyrogram.errors.SessionPasswordNeeded:
        try:
            pwd_info = await c.invoke(GetPassword())
            auth_session["pwd_hint"] = pwd_info.hint
        except: pass
        auth_session["step"] = "password"
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

async def handle_selection(request):
    global selected_emoji_future
    try:
        data = await request.json()
        if selected_emoji_future and not selected_emoji_future.done():
            selected_emoji_future.set_result(data)
        return web.Response(text="OK")
    except Exception as e: return web.Response(status=400, text=str(e))

async def start_web_server():
    global web_app_runner, web_server_port
    app = web.Application(); os.makedirs(DOWNLOADS_DIR, exist_ok=True)
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
async def search_and_select_emoji(
    emoticons: list[str], 
    limit: int = 10, 
    pack_name: str = None, 
    is_animated: bool = None
) -> dict:
    """
    Interactive search for Telegram emojis.
    Args:
        emoticons: List of symbols (e.g. 🔥, 💎). CRITICAL: NO TEXT NAMES.
        limit: Max results per symbol (max 50).
        is_animated: Set to True for animated/video stickers. HIGHLY RECOMMENDED.
    """
    global selected_emoji_future
    cleanup_downloads(); await check_for_updates()
    if not await ensure_authorized() and not await wait_for_auth(): return {"error": "Auth failed"}
    
    app = get_tg_client()
    async with app:
        try:
            # 1. Parallel search for all emoticons
            async def search_one(em):
                try:
                    res = await app.invoke(SearchCustomEmoji(emoticon=em, hash=0))
                    if isinstance(res, EmojiList) and res.document_id:
                        return em, res.document_id[:limit]
                except: pass
                return em, []

            search_results = await asyncio.gather(*(search_one(em) for em in emoticons))
            query_to_ids = {em: ids for em, ids in search_results if ids}
            all_found_ids = [idx for ids in query_to_ids.values() for idx in ids]
            
            if not all_found_ids: return {"error": "No emojis found."}
            
            # 2. Get info for all found stickers in one call
            all_docs = await app.invoke(GetCustomEmojiDocuments(document_id=list(set(all_found_ids))))
            doc_map = {d.id: d for d in all_docs}
            
            # 3. Parallel download of stickers with limit
            semaphore = asyncio.Semaphore(10)
            async def download_one(d):
                async with semaphore:
                    try:
                        mime = getattr(d, 'mime_type', '')
                        is_anim = mime in ('video/webm', 'application/x-tgsticker')
                        if (is_animated is not None and is_animated != is_anim): return None
                        
                        ext = ".webm" if mime == 'video/webm' else (".tgs" if mime == 'application/x-tgsticker' else ".webp")
                        fname = f"emoji_{d.id}{ext}"
                        local_p = os.path.join(DOWNLOADS_DIR, fname)
                        if not os.path.exists(local_p):
                            await app.download_media(FileId(file_type=FileType.STICKER, dc_id=d.dc_id, media_id=d.id, access_hash=d.access_hash, file_reference=d.file_reference).encode(), file_name=local_p)
                        
                        # Pack name
                        p_name = ""
                        for a in d.attributes:
                            if hasattr(a, 'stickerset'):
                                try:
                                    s = await app.invoke(pyrogram.raw.functions.messages.GetStickerSet(stickerset=a.stickerset, hash=0))
                                    p_name = s.set.short_name
                                except: pass
                        
                        if pack_name and pack_name.lower() not in p_name.lower(): return None
                        
                        return {
                            "id": str(d.id), "pack_name": p_name, "is_animated": is_anim, 
                            "local_file_path": os.path.abspath(local_p), "filename": fname
                        }
                    except: return None

            download_tasks = [download_one(doc_map[doc_id]) for doc_id in set(all_found_ids) if doc_id in doc_map]
            downloaded_details = await asyncio.gather(*download_tasks)
            details_map = {det['id']: det for det in downloaded_details if det}
            
            # --- UI Generation ---
            sections_h = ""
            for em_query, ids in query_to_ids.items():
                items_h = ""
                for doc_id in ids:
                    det = details_map.get(str(doc_id))
                    if not det: continue
                    
                    media = f"<video autoplay loop muted src='{det['filename']}'></video>" if det['filename'].endswith('.webm') else (f"<img src='{det['filename']}'>" if not det['filename'].endswith('.tgs') else f"<div id='l_{det['id']}'></div><script>lottie.loadAnimation({{container:document.getElementById('l_{det['id']}'),renderer:'canvas',loop:true,autoplay:true,animationData:{gzip.open(det['local_file_path'],'rt').read()}}})</script>")
                    items_h += f"""<div class='card' onclick='t("{det['id']}", "{em_query}")' id='c_{det['id']}'>
                        <div class='checkbox-box'><input type='radio' name='group_{em_query}' id='i_{det['id']}' data-id='{det['id']}' data-query='{em_query}'></div>
                        {media}<div class='pname'>{det['pack_name']}</div></div>"""
                
                if items_h:
                    sections_h += f"<div class='section'><h3>{em_query}</h3><div class='grid'>{items_h}</div></div>"

            if not sections_h: return {"error": "No results found after filtering"}

            html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><script src='https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js'></script><style>
                body{{background:#0f172a;color:white;font-family:sans-serif;margin:0;padding:20px}}
                .header{{display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;background:#0f172a;padding:10px 0;z-index:100;border-bottom:1px solid #1e293b;margin-bottom:20px}}
                .section{{margin-bottom:30px}}h3{{color:#38bdf8;border-left:4px solid #38bdf8;padding-left:15px;margin-bottom:15px}}
                .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:15px}}
                .card{{background:#1e293b;padding:15px;border-radius:12px;cursor:pointer;border:2px solid transparent;position:relative;text-align:center;transition:0.2s}}
                .card:hover{{background:#334155}}.card.selected{{border-color:#38bdf8;background:#0ea5e922}}
                .checkbox-box{{position:absolute;top:8px;right:8px}}.card video, .card img, .card div{{width:64px;height:64px;margin:0 auto}}
                .pname{{font-size:10px;color:#64748b;margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
                .btn{{background:#0284c7;color:white;border:none;padding:12px 24px;border-radius:8px;cursor:pointer;font-weight:bold}}
                input[type=radio]{{width:18px;height:18px;cursor:pointer}}
            </style></head><body>
                <div class='header'><div><h2 style='margin:0'>Emoji Selection</h2><p style='margin:5px 0 0 0;font-size:12px;color:#94a3b8'>Select one per search query</p></div><button onclick='s()' id='sub' class='btn'>Confirm</button></div>
                {sections_h}
                <script>
                    function t(id, q){{
                        document.querySelectorAll('input[data-query="'+q+'"]').forEach(rb => document.getElementById('c_'+rb.dataset.id).classList.remove('selected'));
                        const c=document.getElementById('c_'+id), i=document.getElementById('i_'+id);
                        i.checked=true; c.classList.add('selected');
                    }}
                    async function s(){{
                        const b=document.getElementById('sub'); b.disabled=true; b.innerText='Sending...';
                        const res=[]; document.querySelectorAll('input:checked').forEach(i=>res.push({{id:i.dataset.id,query:i.dataset.query}}));
                        if(!res.length) {{ alert('Please select at least one!'); b.disabled=false; b.innerText='Confirm'; return; }}
                        try {{
                            await fetch('/select',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{selections:res}})}});
                            window.close();
                        }} catch(e) {{ alert('Error'); b.disabled=false; }}
                    }}
                </script></body></html>"""
            
            with open(os.path.join(DOWNLOADS_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(html)
            base_url = f"http://127.0.0.1:{web_server_port}" if web_app_runner else await start_web_server()
            webbrowser.open(f"{base_url}/static/index.html")
            
            selected_emoji_future = asyncio.Future()
            try:
                raw_res = await asyncio.wait_for(selected_emoji_future, 300.0)
                mapping = {sel['query']: [sel['id']] for sel in raw_res.get("selections", [])}
                cleanup_downloads(); return {"status": "success", "selection_mapping": mapping}
            except: return {"error": "Timeout"}
        except Exception as e: return {"error": str(e)}

@mcp.tool()
async def search_emoji_auto(emoticons: list[str], limit: int = 5, pack_name: str = None, is_animated: bool = None) -> dict:
    """Non-interactive search for Telegram emojis. returns mapping. Unicode symbols only."""
    await check_for_updates()
    if not await ensure_authorized() and not await wait_for_auth(): return {"error": "Auth failed"}
    app = get_tg_client()
    async with app:
        try:
            # Parallel search
            async def search_one(em):
                try:
                    res = await app.invoke(SearchCustomEmoji(emoticon=em, hash=0))
                    if isinstance(res, EmojiList) and res.document_id: return em, res.document_id[:limit]
                except: pass
                return em, []

            results = await asyncio.gather(*(search_one(em) for em in emoticons))
            query_to_ids = {em: ids for em, ids in results if ids}
            all_ids = [idx for ids in query_to_ids.values() for idx in ids]
            
            if not all_ids: return {"error": "No results"}
            docs = await app.invoke(GetCustomEmojiDocuments(document_id=list(set(all_ids))))
            
            final_res = []
            for d in docs:
                p_name = ""
                for a in d.attributes:
                    if hasattr(a, 'stickerset'):
                        try:
                            s = await app.invoke(pyrogram.raw.functions.messages.GetStickerSet(stickerset=a.stickerset, hash=0))
                            p_name = s.set.short_name
                        except: pass
                mime = getattr(d, 'mime_type', '')
                is_anim = mime in ('video/webm', 'application/x-tgsticker')
                if (pack_name and pack_name.lower() not in p_name.lower()) or (is_animated is not None and is_animated != is_anim): continue
                final_res.append({"id": str(d.id), "pack_name": p_name, "is_animated": is_anim})
            return {"status": "success", "results": final_res}
        except Exception as e: return {"error": str(e)}

def main():
    logger.info(f"Remoji TG MCP v{VERSION}. Data: {BASE_DIR}")
    cleanup_downloads(); mcp.run()

if __name__ == "__main__": main()
