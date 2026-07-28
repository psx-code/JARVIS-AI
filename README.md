# J.A.R.V.I.S — By Poorna

> **Just A Rather Very Intelligent System**  
> A fully local, voice-driven AI assistant built for Windows — inspired by Tony Stark's JARVIS.

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-cyan?style=flat-square)
![Gemini](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-orange?style=flat-square&logo=google)
![OpenRouter](https://img.shields.io/badge/Fallback-OpenRouter-purple?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?style=flat-square&logo=windows)

---

## What is this?

JARVIS is a real-time, always-listening voice AI assistant that runs on your Windows PC. It uses Google's Gemini Live API for native audio — meaning it hears you speak, thinks, and speaks back in a natural voice with no push-to-talk required. Every capability is triggered by voice, with no typing needed.

---

## Capabilities

### 🎙️ Voice & Conversation
- **Native real-time audio** via Gemini 2.5 Flash Live API — no wake word, just talk
- **Speaks back** in a natural voice (Charon voice model)
- **Text input fallback** — type commands if you prefer
- **Long-term memory** — remembers facts about you across sessions (name, preferences, projects, relationships) and uses them in conversation
- **Conversation logging** — every exchange shown in the activity log with typewriter animation

### 🖥️ Computer Control
- **Open any app** — "Open WhatsApp", "Launch Spotify", "Start Chrome"
- **System settings** — volume, brightness, WiFi, dark mode, lock screen, restart, shutdown
- **Keyboard shortcuts & hotkeys** — trigger any key combination by voice
- **Mouse control** — click, double-click, right-click, scroll, move to coordinates
- **Screenshot** — capture and save your screen
- **Type text on screen** — dictate text into any field
- **Window management** — focus, close, fullscreen any window
- **Scroll & zoom** — control page scroll and zoom level

### 🌐 Web & Browser
- **Web search** — search anything, get spoken summaries
- **Browser control** — open URLs, click elements, fill forms, scroll pages, switch tabs
- **Smart click** — describe an element in natural language and JARVIS clicks it
- **Incognito mode** — open tabs privately by voice

### 💬 Messaging
- **WhatsApp** — send messages to any contact by voice
- **Telegram** — send messages to any Telegram contact
- **Instagram DMs** — send direct messages via browser
- **Any messaging app** — generic support for Messenger, Discord, Signal, and others

### 😴 Away Mode (Auto-Reply)
- **Screen monitoring** — when you're asleep or in a meeting, JARVIS watches WhatsApp every 30 seconds
- **Auto-detects unread messages** using pixel color scanning (no API needed)
- **Auto-replies** with a customizable message on your behalf
- **Escalation** — urgent messages (emergency, accident, hospital) are flagged and spoken aloud, never auto-replied to
- **Cooldown** — won't spam the same person with repeated replies
- **Whitelist / blacklist** — control exactly who gets auto-replied to
- **Briefing** — when you say "I'm back", JARVIS reads you a full summary of everything that happened
- **Configurable message** — set your own away reply text in one line of code

### 📁 File Management
- **List, create, delete, move, copy, rename** files and folders by voice
- **Read and write** file contents
- **Find files** by name or extension across your system
- **Disk usage** — check storage stats
- **Organize desktop** — auto-sort files by type or date

### 📂 File Processing (Upload & Analyze)
- **Images** — describe, OCR, resize, compress, convert
- **PDFs** — summarize, extract text, convert to Word
- **Word docs** — summarize, fix grammar, reformat, translate
- **Excel / CSV** — analyze, stats, filter, sort, convert
- **JSON / XML** — validate, format, analyze
- **Code files** — explain, review, fix, optimize, run, generate tests
- **Audio** — transcribe, trim, convert
- **Video** — trim, extract audio, extract frames, compress, transcribe
- **Archives** — list and extract ZIP/RAR/7Z
- **PowerPoint** — summarize and extract text

### 🎬 YouTube
- **Play videos** — "Play lofi hip hop on YouTube"
- **Summarize** — get a spoken summary of any video
- **Video info** — title, views, duration by URL
- **Trending** — fetch trending videos by country

### 🌤️ Weather
- **Real-time weather** for any city — spoken report with conditions and temperature

### ✈️ Flights
- **Search Google Flights** by voice — origin, destination, date, cabin class, passengers
- Results spoken aloud or saved to Notepad

### ⏰ Reminders
- **Set timed reminders** via Windows Task Scheduler
- Specify date, time, and message — fires a notification even if JARVIS is closed

### 🖥️ Desktop Control
- **Change wallpaper** — by file path or URL
- **Organize desktop** — sort by type or date
- **Clean and list** desktop files
- **Desktop stats** — file count, size breakdown

### 💻 Code Assistant
- **Write code** — describe what you want, JARVIS writes and saves it
- **Edit existing files** — describe the change, JARVIS applies it
- **Explain code** — get a spoken plain-English explanation
- **Run code** — execute scripts and hear the output
- **Build projects** — compile and run with dependency handling

### 🏗️ Dev Agent
- **Full project scaffolding** — describe an app idea, JARVIS plans it, writes all files, installs dependencies, opens VS Code, runs it, and auto-fixes errors
- Supports Python, JavaScript, and more

### 🎮 Game Updater (Steam & Epic)
- **Update games** — trigger Steam/Epic updates by voice
- **Install games** by name or AppID
- **List installed games**
- **Check download status**
- **Schedule updates** for off-hours
- **Shutdown when done** — PC powers off automatically after download completes

### 🔍 Agent Tasks
- **Multi-step automation** — "Research X and save to a file", "Find all PDFs in Downloads and organize them"
- Chains multiple tools together autonomously with priority levels

### 📸 Screen & Camera Vision
- **Analyze your screen** — "What's on my screen?" — JARVIS sees and describes it
- **Webcam analysis** — "Look at what I'm holding"
- Powered by Gemini's vision model via a persistent live session

### 🧠 Memory System
- Automatically extracts and saves important facts from conversation
- Remembers: name, age, city, job, preferences, hobbies, projects, relationships, future plans
- Memory is injected into every session so JARVIS always knows who you are
- User-editable — tell JARVIS to remember or forget anything

---

## HUD Interface

Built with **PyQt6** — a custom animated interface featuring:

- **Dot sphere** — hundreds of points arranged in a golden-ratio sphere that morphs, breathes, and vibrates in real time based on voice activity
- **Circular audio waveform** — 64-bar ring around the sphere that spikes when speaking
- **Arc reactor core** — glowing energy center with rotating spokes and radial gradient
- **Hexagonal grid background** — animated hex cells across the entire display
- **Circular system gauges** — CPU, MEM, NET, GPU, TMP as animated arc gauges
- **Scrolling telemetry ticker** — live system data scrolling across the footer
- **State-based color shifts** — cyan (listening), orange (speaking), amber (thinking), red (muted)
- **Typewriter activity log** — color-coded log with smooth character-by-character animation
- **Drag-and-drop file zone** — drop any file to process it
- **Real-time system monitor** — CPU, memory, network, GPU, temperature, uptime, process count
- **Clock and date display** in the header
- **F4** to mute/unmute · **F11** for fullscreen

---

## Tech Stack

| Component | Technology |
|---|---|
| AI Engine | Google Gemini 2.5 Flash (Live Audio API) |
| Fallback LLM | OpenRouter (nvidia/nemotron and others) |
| UI Framework | PyQt6 |
| Voice I/O | sounddevice + Gemini native audio |
| Screen Capture | mss |
| Computer Control | pyautogui |
| System Metrics | psutil |
| Browser Automation | Playwright / pyautogui |
| Memory Storage | JSON (local) |

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/Mark-XXXIX-OR.git
cd Mark-XXXIX-OR

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py
```

On first launch, a setup screen will appear asking for:
- **Gemini API key** — from [aistudio.google.com](https://aistudio.google.com)
- **OpenRouter API key** — from [openrouter.ai](https://openrouter.ai)
- **Your OS** — auto-detected

---

## Voice Command Examples

```
"Open WhatsApp and send a message to Mom saying I'll be home by 8"
"What's the weather in Mumbai?"
"Search for the latest news about AI"
"I'm going to sleep, watch my WhatsApp"
"Play lofi music on YouTube"
"Take a screenshot and save it to my desktop"
"Set a reminder for tomorrow at 9am to call the doctor"
"Find flights from Delhi to Bangalore next Friday"
"Update all my Steam games"
"I'm back" → JARVIS briefs you on missed messages
"Goodbye" → JARVIS shuts down
```

---

## Project Structure

```
JARVIS px1tr/
├── main.py                  # Entry point, JARVIS core loop
├── ui.py                    # PyQt6 HUD interface
├── or_client.py             # OpenRouter LLM client
├── actions/
│   ├── open_app.py          # App launcher
│   ├── send_message.py      # WhatsApp/Telegram/Instagram
│   ├── auto_reply.py        # Away mode autoresponder
│   ├── notification_watcher.py
│   ├── browser_control.py   # Playwright browser automation
│   ├── computer_control.py  # pyautogui control
│   ├── computer_settings.py # System settings
│   ├── screen_processor.py  # Vision/screenshot analysis
│   ├── file_controller.py   # File management
│   ├── file_processor.py    # File analysis (PDF/image/video/etc)
│   ├── code_helper.py       # Code writing/running
│   ├── dev_agent.py         # Full project builder
│   ├── web_search.py        # Web search
│   ├── weather_report.py    # Weather
│   ├── youtube_video.py     # YouTube control
│   ├── reminder.py          # Task scheduler reminders
│   ├── flight_finder.py     # Google Flights scraper
│   ├── desktop.py           # Desktop control
│   └── game_updater.py      # Steam/Epic Games
├── agent/
│   └── task_queue.py        # Multi-step agent task queue
├── memory/
│   └── memory_manager.py    # Long-term memory system
├── core/
│   └── prompt.txt           # JARVIS system prompt
└── config/
    └── api_keys.json        # API keys (gitignored)
```

---

## Credits

Built by **Poorna** — a personal AI assistant project inspired by Iron Man's JARVIS.  
Powered by Google Gemini, OpenRouter, and a lot of Python.

---

*"Sometimes you gotta run before you can walk." — Tony Stark*
