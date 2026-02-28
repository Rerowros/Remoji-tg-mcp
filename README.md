# Remoji-TG-MCP 🎭

[![PyPI version](https://img.shields.io/pypi/v/remoji-tg-mcp.svg)](https://pypi.org/project/remoji-tg-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English](#english) | [Русский](#русский)

---

<a name="english"></a>
## English

Telegram Emoji Search & Selection MCP Server. This tool allows AI models to search for custom Telegram stickers/emojis and lets you visually select the best ones via a web interface.

### ✨ Features
- **Grouped Search:** Results are organized by your search queries.
- **Performance:** High-speed rendering for 50+ animated emojis.
- **Silent Auth:** Silent waiting for user login in the browser.
- **Data Safety:** Files are stored in a dedicated system folder (AppData/Roaming).

### 🛠 Prerequisites
You must have **uv** installed:
- **Windows:** `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS/Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 🚀 Installation Guide

#### 1. Claude Desktop
Add this to your `%AppData%\Roaming\Claude\claude_desktop_config.json`:
```json
"mcpServers": {
  "remoji-tg-mcp": {
    "command": "uvx",
    "args": ["--refresh", "remoji-tg-mcp"]
  }
}
```

#### 2. VS Code (Cline / Roo Code / MCP Client)
Add to your extension's MCP settings:
```json
"emoji-tg-mcp": {
  "command": "uvx",
  "args": ["--refresh", "remoji-tg-mcp"]
}
```

#### 3. Cursor
1. Go to **Settings** -> **General** -> **MCP**.
2. Click **+ Add Agent**.
3. Name: `Telegram-Emoji`, Type: `command`, Command: `uvx --refresh remoji-tg-mcp`.

#### 4. Windsurf
Add to your `mcp_config.json` or MCP panel:
```json
"remoji-tg-mcp": {
  "command": "uvx",
  "args": ["--refresh", "remoji-tg-mcp"]
}
```

---

<a name="русский"></a>
## Русский

MCP-сервер для поиска и выбора кастомных эмодзи Telegram. Позволяет нейросетям искать стикеры и предоставляет веб-интерфейс для выбора.

### 🛠 Предварительные требования
У вас должен быть установлен **uv**:
- **Windows:** `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS/Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 🚀 Инструкция по установке

#### 1. Claude Desktop
Добавьте в `%AppData%\Roaming\Claude\claude_desktop_config.json`:
```json
"mcpServers": {
  "remoji-tg-mcp": {
    "command": "uvx",
    "args": ["--refresh", "remoji-tg-mcp"]
  }
}
```

#### 2. VS Code (Cline / Roo Code)
Вставьте в настройки MCP вашего расширения:
```json
"emoji-tg-mcp": {
  "command": "uvx",
  "args": ["--refresh", "remoji-tg-mcp"]
}
```

#### 3. Cursor
1. **Settings** -> **General** -> **MCP**.
2. **+ Add Agent**.
3. Name: `Telegram-Emoji`, Type: `command`, Command: `uvx --refresh remoji-tg-mcp`.

#### 4. Windsurf
Добавьте в конфигурацию MCP:
```json
"remoji-tg-mcp": {
  "command": "uvx",
  "args": ["--refresh", "remoji-tg-mcp"]
}
```

### ⚙️ Настройка и безопасность
При первом запуске откроется браузер для ввода **API ID** и **API HASH** ([my.telegram.org](https://my.telegram.org/apps)).

**Где лежат данные?**
- **Windows:** `%AppData%\Roaming\remoji-tg-mcp`
- **macOS/Linux:** Стандартные папки данных пользователя.

**Шифрование:**
Добавьте `SESSION_PASSWORD="пароль"` в файл `.env` в папке данных для защиты файла сессии.
