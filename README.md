# Remoji-tg-mcp 🚀

An advanced Model Context Protocol (MCP) server for AI assistants (like Claude, Cursor, Windsurf) that allows them to search and retrieve IDs of Telegram Premium custom emojis.

Unlike other solutions that rely on third-party websites and generate heavy sprite sheets for the AI to "look" at, **Remoji-tg-mcp** takes a smarter, more efficient approach.

## ✨ Why Remoji is Better

1. **Direct Telegram Search (Userbot)**: Uses `pyrogram` to act as a real Telegram user. It searches for emojis directly within Telegram's native search engine, just like you would in the app. No reliance on external databases like `fstik.app`.
2. **Interactive Browser UI**: Instead of forcing the LLM to "see" and guess emojis from generated images (which consumes a massive amount of tokens), Remoji spins up a local web server. It opens a beautiful, interactive UI in your browser where **you** click the exact animated emoji you want.
3. **Massive Token Savings**: By offloading the visual selection to the human user via the browser, the LLM doesn't need to process images. It just receives the exact `custom_emoji_id` instantly.
4. **Full Animation Support**: Renders both `.tgs` (Lottie animated stickers) and `.webm` (video stickers) right in your browser for accurate previewing.

## 🛠️ Prerequisites

- Python 3.13+
- A Telegram account (to act as the Userbot)
- Your Telegram `API_ID` and `API_HASH` (Get them from [my.telegram.org](https://my.telegram.org))

## 📦 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Remoji-tg-mcp.git
   cd Remoji-tg-mcp
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: You can generate `requirements.txt` using `pip freeze > requirements.txt` if not already present, or just install `mcp`, `pyrogram`, `tgcrypto`, `aiohttp`)*

3. **First Run (Authentication)**:
   Before using it as an MCP server, you need to log in to your Telegram account to generate the `user_session.session` file.
   Run the test script and follow the prompts to enter your phone number and login code:
   ```bash
   python test_emoji.py
   ```
   *Security Note: The `.session` file contains your account access. It is included in `.gitignore` and should **never** be shared or committed.*

## ⚙️ MCP Configuration (VS Code / Cursor / Claude)

Add the server to your MCP configuration file (e.g., `mcp.json` or `claude_desktop_config.json`).

```json
{
  "mcpServers": {
    "remoji-tg": {
      "command": "python",
      "args": [
        "C:/path/to/your/Remoji-tg-mcp/tg_emoji_mcp.py"
      ],
      "env": {
        "TG_API_ID": "YOUR_API_ID_HERE",
        "TG_API_HASH": "YOUR_API_HASH_HERE"
      }
    }
  }
}
```

## 🧰 Available Tools

### 1. `search_and_select_emoji` (Default & Recommended)
Searches for custom emojis based on base emojis (e.g., `["❌", "🔴"]`). It downloads the animations, starts a local web server, and opens your browser. You visually pick the emoji you want, and the tool returns the exact ID to the AI.

### 2. `search_emoji_auto` (Non-Interactive)
Searches for custom emojis and returns a raw list of results (IDs and metadata) directly to the AI without opening a browser. Useful for automated tasks where human interaction isn't possible.

## 🔒 Security

- **No Hardcoded Credentials**: Uses environment variables (`TG_API_ID`, `TG_API_HASH`).
- **Local Only**: The interactive web server binds to `localhost` on a random available port.
- **Session Protection**: The `.gitignore` ensures your `user_session.session` stays on your machine.

## 📄 License

MIT License
