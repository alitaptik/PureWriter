# PureWriter — App Specification

## Overview

A minimal, distraction-free writing app built in Python with PyQt6, with ElevenLabs TTS playback per paragraph. Designed for a single user on macOS. Not deployed — runs locally.

---

## Tech Stack

- **Language:** Python 3
- **UI:** PyQt6
- **TTS:** ElevenLabs API (via `elevenlabs` Python SDK or direct HTTP requests)
- **Audio playback:** `pygame` or `sounddevice` for inline playback without saving files
- **Config:** `~/.purewriter/config.json` (stores API key and last used voice ID)

---

## Editor

- Clean, distraction-free text editor (single font, no toolbar)
- Supports plain text (`.txt`) and Markdown (`.md`) files
- No rich text rendering — raw text editing only
- Paragraphs are the atomic unit, defined by blank lines between blocks of text
- File operations: Open, Save, Save As via menu or keyboard shortcuts
- Window title shows current filename

---

## TTS Behaviour

- **Trigger 1:** Small play button (▶) appears in the left margin next to the paragraph where the cursor is currently located
- **Trigger 2:** Keyboard shortcut `Cmd+R` plays the paragraph where the cursor is
- On trigger: the current paragraph text is sent to the ElevenLabs API using the selected voice ID
- Audio streams/plays inline — no file is written to disk unless explicitly exported
- Only one paragraph plays at a time; triggering another stops the current one
- A stop button or pressing `Cmd+R` again stops playback

---

## Voice Selection

- Sidebar or toolbar dropdown populated dynamically by calling the ElevenLabs `/v1/voices` endpoint on launch
- Lists all voices available on the account: premade, cloned, and shared
- Shows voice name; stores voice ID internally
- Last used voice is saved to config and restored on next launch

---

## API Key Management

- On first launch, prompt user to enter ElevenLabs API key
- Key is saved to `~/.purewriter/config.json`
- Settings menu option to update the key later
- Key is never logged or displayed in plain text after saving

---

## Config File Structure

```json
{
  "api_key": "sk_...",
  "last_voice_id": "VOICE_ID_HERE",
  "window_width": 900,
  "window_height": 700
}
```

---

## What This App Does NOT Do

- No formatting toolbar or rich text
- No cloud sync
- No auto-play as you type
- No full-document TTS (paragraph only)
- No character batching or caching
- No collaboration features
- No deployment or packaging required

---

## File Structure (suggested)

```
purewriter/
├── main.py          # Entry point
├── editor.py        # PyQt6 editor widget
├── tts.py           # ElevenLabs API calls and audio playback
├── config.py        # Config read/write
├── voices.py        # Voice list fetching and dropdown logic
└── requirements.txt
```

---

## Requirements

```
PyQt6
elevenlabs
pygame
requests
```
