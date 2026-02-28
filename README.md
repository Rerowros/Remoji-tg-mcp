# Remoji-TG-MCP 🎭

[![PyPI version](https://img.shields.io/pypi/v/remoji-tg-mcp.svg)](https://pypi.org/project/remoji-tg-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP (Model Context Protocol) server that empowers AI models (Claude, Gemini, etc.) to search for custom Telegram stickers and emojis. It features an interactive web-based selection tool and high-speed parallel processing.

[English](#english) | [Русский](#русский)

---

<a name="english"></a>
## English

### ✨ Key Features
- **Interactive Visual Selection:** Pick the perfect emoji via a local web interface.
- **High-Speed Processing:** Parallel searching and sticker downloading (3-5x faster than sequential).
- **Smooth Animation:** Uses Canvas rendering for 50+ animated stickers without browser lag.
- **Zero-Terminal Auth:** Handle phone entry, OTP codes, and 2FA password hints entirely in your browser.
- **Data Isolation:** All sensitive data is stored safely in your system's AppData/Home directory.
- **Auto-Cleanup:** Temporary preview files are instantly deleted after you make a choice.

### 🛠 Prerequisites
You must have **uv** (modern Python package manager) installed:
- **Windows:** `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS/Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 🚀 Installation Guide

#### 1. Claude Desktop
Open `%AppData%\Roaming\Claude\claude_desktop_config.json` and add:
```json
"mcpServers": {
  "remoji-tg-mcp": {
    "command": "uvx",
    "args": ["--refresh", "remoji-tg-mcp"]
  }
}
```

#### 2. VS Code (Cline / Roo Code / MCP Client)
Add to your extension's MCP configuration:
```json
"emoji-tg-mcp": {
  "command": "uvx",
  "args": ["--refresh", "remoji-tg-mcp"]
}
```

#### 3. Cursor (AI Editor)
1. Navigate to **Settings** -> **General** -> **MCP**.
2. Click **+ Add Agent**.
3. **Name:** `Telegram-Emoji`, **Type:** `command`, **Command:** `uvx --refresh remoji-tg-mcp`.

#### 4. Windsurf
Add to your `mcp_config.json` or MCP control panel:
```json
"remoji-tg-mcp": {
  "command": "uvx",
  "args": ["--refresh", "remoji-tg-mcp"]
}
```

### ⚙️ Configuration & Security

On the first run, the server will open a browser tab asking for:
1. **API ID / HASH:** Obtain these at [my.telegram.org](https://my.telegram.org/apps).
2. **Phone Number:** Enter in any format (auto-formatted to international).
3. **2FA Password:** Supports password hints if enabled.

#### Data Locations
- **Windows:** `%AppData%\Roaming\remoji-tg-mcp`
- **macOS/Linux:** Standard user data paths.

**Encryption:** To encrypt your `.session` file, add `SESSION_PASSWORD="your_password"` to the `.env` file located in the data directory above.

---

<a name="русский"></a>
## Русский

### ✨ Основные возможности
- **Интерактивный выбор:** Выбирайте идеальный эмодзи через удобный локальный веб-интерфейс.
- **Высокая скорость:** Параллельный поиск и загрузка стикеров (в 3-5 раз быстрее обычного способа).
- **Плавная анимация:** Использование Canvas-рендеринга позволяет просматривать 50+ анимированных стикеров без тормозов.
- **Авторизация без терминала:** Ввод телефона, кода подтверждения и подсказка пароля 2FA — всё в браузере.
- **Безопасность:** Чувствительные данные хранятся в изолированной системной папке AppData.
- **Авто-очистка:** Временные файлы превью удаляются сразу после завершения выбора.

### 🛠 Предварительные требования
У вас должен быть установлен **uv**:
- **Windows:** `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS/Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 🚀 Инструкция по установке

#### 1. Claude Desktop
Откройте `%AppData%\Roaming\Claude\claude_desktop_config.json` и добавьте:
```json
"mcpServers": {
  "remoji-tg-mcp": {
    "command": "uvx",
    "args": ["--refresh", "remoji-tg-mcp"]
  }
}
```

#### 2. VS Code (Cline / Roo Code)
Добавьте в настройки MCP вашего расширения:
```json
"emoji-tg-mcp": {
  "command": "uvx",
  "args": ["--refresh", "remoji-tg-mcp"]
}
```

#### 3. Cursor
1. Откройте **Settings** -> **General** -> **MCP**.
2. Нажмите **+ Add Agent**.
3. **Name:** `Telegram-Emoji`, **Type:** `command`, **Command:** `uvx --refresh remoji-tg-mcp`.

#### 4. Windsurf
Добавьте в конфигурацию MCP:
```json
"remoji-tg-mcp": {
  "command": "uvx",
  "args": ["--refresh", "remoji-tg-mcp"]
}
```

### ⚙️ Настройка и защита данных

При первом запуске сервер откроет вкладку в браузере и запросит:
1. **API ID / HASH:** Получите их на [my.telegram.org](https://my.telegram.org/apps).
2. **Номер телефона:** В любом формате (сервер сам исправит на международный).
3. **Пароль 2FA:** Поддерживается отображение подсказки к паролю.

#### Где хранятся данные?
- **Windows:** `C:\Users\Имя\AppData\Roaming\remoji-tg-mcp`
- **macOS/Linux:** Стандартные папки данных пользователя.

**Шифрование:** Чтобы зашифровать файл сессии, добавьте строку `SESSION_PASSWORD="ваш_пароль"` в файл `.env`, который находится в папке данных (путь выше).

### 🔄 Обновление
Если вы используете флаг `--refresh` в конфигах (как в примерах выше), сервер будет обновляться **автоматически** при каждом запуске IDE или Claude.
