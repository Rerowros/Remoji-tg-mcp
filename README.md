# Remoji-TG-MCP

Telegram Emoji Search & Selection MCP Server for Gemini CLI.

## ✨ Features
- **Multi-Emoji Search**: Search for multiple emoticons at once.
- **Visual Selection**: Opens a web UI to choose your preferred stickers for each emoji.
- **API Setup UI**: If credentials are missing, it opens a configuration page in your browser.
- **Modern Installation**: Supports `uvx` for zero-config setup.

## 🚀 Installation

Add the following to your `mcp.json` configuration file:

### Using `uvx`
```json
"remoji-tg-mcp": {
  "command": "uvx",
  "args": ["git+https://github.com/Rerowros/tg_mcp.git"]
}
```


## ⚙️ Configuration
The server will automatically ask for `TG_API_ID` and `TG_API_HASH` via a web interface on the first run. These are saved in a local `.env` file.


