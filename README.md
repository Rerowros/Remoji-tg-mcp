# Remoji-TG-MCP 🎭

[![PyPI version](https://img.shields.io/pypi/v/remoji-tg-mcp.svg)](https://pypi.org/project/remoji-tg-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English](#english) | [Русский](#русский)

---

<a name="english"></a>
## English

Telegram Emoji Search & Selection MCP Server. This tool allows AI models (like Claude or Gemini) to search for custom Telegram stickers/emojis and lets you visually select the best ones via a web interface.

### ✨ Features
- **Interactive Selection:** Opens a local web UI for you to pick the perfect emoji.
- **Web-based Auth:** No terminal input needed. Phone, OTP, and 2FA password are all handled in your browser.
- **Auto-Cleanup:** Temporary preview files are automatically deleted after selection.
- **Session Security:** Optional encryption for your session file.
- **Update Notifications:** Notifies you in the logs when a new version is available on PyPI.

### 🚀 Quick Start (Claude Desktop)

Add this to your `claude_desktop_config.json`:

```json
"mcpServers": {
  "remoji-tg-mcp": {
    "command": "uvx",
    "args": ["remoji-tg-mcp"]
  }
}
```

### ⚙️ Configuration & Data Security

On the first run, the server will open a browser tab asking for your **Telegram API ID** and **API HASH** (get them at [my.telegram.org](https://my.telegram.org/apps)).

#### Where is my data stored?
By default, the server creates files in the directory from which the host (e.g., Claude) was started:
- `.env`: Stores your API credentials.
- `user_session.session`: Your Telegram session (Auth Key).
- `downloads/`: Temporary folder for emoji previews (auto-cleaned).

#### 🛡️ Protecting Sensitive Data
To protect your `.session` file, you can add `SESSION_PASSWORD="your_password"` to your `.env` file. If set, the session file will be encrypted using this password.

---

<a name="русский"></a>
## Русский

MCP-сервер для поиска и выбора кастомных эмодзи Telegram. Этот инструмент позволяет нейросетям (Claude, Gemini) искать стикеры и предоставляет вам удобный веб-интерфейс для выбора наиболее подходящих вариантов.

### ✨ Особенности
- **Интерактивный выбор:** Модель открывает страницу в браузере, где вы сами кликаете на нужные эмодзи.
- **Авторизация в браузере:** Код подтверждения (OTP) и пароль 2FA вводятся через веб-форму — никакой работы с терминалом.
- **Авто-очистка:** Все временные файлы превью удаляются сразу после того, как вы подтвердили выбор.
- **Безопасность сессии:** Поддержка шифрования файла сессии паролем.
- **Проверка обновлений:** Сервер подскажет в логах, если на PyPI вышла новая версия.

### 🚀 Быстрый старт (Claude Desktop)

Добавьте в ваш конфиг `claude_desktop_config.json`:

```json
"mcpServers": {
  "remoji-tg-mcp": {
    "command": "uvx",
    "args": ["remoji-tg-mcp"]
  }
}
```

### ⚙️ Настройка и безопасность данных

При первом запуске сервер откроет вкладку в браузере и попросит ввести **API ID** и **API HASH** (их нужно получить на [my.telegram.org](https://my.telegram.org/apps)).

#### Где хранятся данные?
Файлы создаются в рабочей директории процесса, запустившего сервер (обычно это корень вашего профиля пользователя):
- `.env`: Хранит ваши API ключи.
- `user_session.session`: Файл сессии Telegram (ключ доступа к аккаунту).
- `downloads/`: Папка для временных превью (очищается автоматически).

#### 🛡️ Защита чувствительных данных
Чтобы защитить файл сессии, вы можете вручную добавить строку `SESSION_PASSWORD="ваш_пароль"` в файл `.env`. В этом случае файл `.session` будет зашифрован этим паролем.

### 🛠 Обновление
Если сервер сообщил о наличии новой версии, выполните:
```bash
uv tool upgrade remoji-tg-mcp
```
