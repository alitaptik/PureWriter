# PureWriter

A minimal, distraction-free writing app for macOS. Write in plain text or Markdown, then listen to each paragraph read back in any ElevenLabs voice while you edit.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)

## Features

- **Distraction-free editor** — clean single-font writing surface, no toolbar clutter
- **ElevenLabs TTS** — plays any paragraph in any voice from your account, including cloned voices
- **Word-level highlighting** — the spoken word is highlighted in real time as audio plays
- **Play from cursor** — `Cmd+R` plays from wherever your cursor is, not just from the top
- **Emotion tags** — type `[calm]`, `[excited]`, `[whisper]` etc. directly in your text (supported by `eleven_v3`)
- **Live Markdown styling** — headers, bold, italic, code, blockquotes rendered inline as you type
- **Markdown preview panel** — toggle a side-by-side rendered preview with `Cmd+Shift+P`
- **Light / dark theme** — toggle with `Cmd+Shift+T`, preference saved
- **Session character counter** — see how many characters you've sent to ElevenLabs this session
- **Pause / resume** — player bar with ▶ ⏸ ⏹ controls
- **Voice selector** — all voices on your account loaded on launch, last used voice remembered

## Requirements

- macOS (uses `sounddevice` for audio)
- Python 3.11+
- An [ElevenLabs](https://elevenlabs.io) account and API key

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/PureWriter.git
cd PureWriter/purewriter
pip install -r requirements.txt
python3 main.py
```

On first launch you will be prompted for your ElevenLabs API key. It is stored in `~/.purewriter/config.json` and never logged.

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Cmd+R` | Play from cursor / Stop |
| `Cmd+Shift+T` | Toggle light / dark theme |
| `Cmd+Shift+P` | Toggle Markdown preview panel |
| `Cmd+N` | New file |
| `Cmd+O` | Open file |
| `Cmd+S` | Save |
| `Cmd+Shift+S` | Save As |

## ElevenLabs Voice Tags

With `eleven_v3`, you can embed emotion cues directly in your text:

```
[excited] This is the part where things get interesting.
[calm] And here we slow down again.
[whisper] Secrets go here.
```

## Config

Stored at `~/.purewriter/config.json`:

```json
{
  "api_key": "sk_...",
  "last_voice_id": "...",
  "window_width": 900,
  "window_height": 700,
  "theme": "dark",
  "preview_visible": false
}
```

## License

MIT
