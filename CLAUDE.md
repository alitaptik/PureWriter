# PureWriter — Project Reference for Claude

## What this is
A PyQt6 distraction-free writing app with ElevenLabs TTS narration.
Run with: `python purewriter/main.py` (after `pip install -r purewriter/requirements.txt`).

## File map
| File | Purpose |
|---|---|
| `purewriter/main.py` | Main window, menus, theming, voice loading, file I/O |
| `purewriter/editor.py` | `Editor` widget — QPlainTextEdit with margin play buttons and word highlighting |
| `purewriter/tts.py` | ElevenLabs TTS call, audio playback, pause/stop threading |
| `purewriter/highlighter.py` | Markdown + SSML syntax highlighting (PyQt6 QSyntaxHighlighter) |
| `purewriter/config.py` | JSON config at `~/.purewriter/config.json` |
| `purewriter/voices.py` | Fetches voice list from ElevenLabs v2 API |
| `purewriter/rtf_io.py` | RTF import (`striprtf`) and minimal RTF export |

## ElevenLabs API details
- Endpoint: `POST /v1/text-to-speech/{voice_id}/with-timestamps`
- Model: `eleven_turbo_v2_5`
- `enable_ssml_parsing: true` — supports `<break>`, `<emphasis>`, `<phoneme>` tags
- `voice_settings` are sent explicitly on every call (stability 0.55, similarity_boost 0.75, style 0.0) to prevent emotional drift between paragraphs
- Voice list: `GET /v2/voices?page_size=100` with pagination via `next_page_token`

## Config keys stored in `~/.purewriter/config.json`
`api_key`, `last_voice_id`, `window_width`, `window_height`, `theme` ("dark"/"light"), `preview_visible`

## Keyboard shortcuts
| Shortcut | Action |
|---|---|
| Ctrl+R | Play / Stop current paragraph |
| Ctrl+N | New file |
| Ctrl+O | Open file |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| Ctrl+Shift+T | Toggle dark/light theme |
| Ctrl+Shift+P | Toggle Markdown preview |

## Supported file formats
- `.txt`, `.md` — plain UTF-8 read/write
- `.rtf` — import via `striprtf`, export via minimal RTF envelope in `rtf_io.py`

## SSML tags (Insert Tag menu under Edit)
- `<break time="500ms"/>` / `<break time="1s"/>` — pause
- `<emphasis level="strong">…</emphasis>` — wraps selection
- `<phoneme alphabet="ipa" ph="…">…</phoneme>` — wraps selection
Tags are highlighted teal in the editor.

## Word highlighting during playback
`editor.py:highlight_word(char_start, char_end)` — maps ElevenLabs character-level alignment back to original text (accounting for stripped tags). Uses yellow `#e5c07b` background.

## Known quirks / decisions
- TTS runs in a daemon thread; word callbacks are routed through `_WordBridge` (a `QObject` with `pyqtSignal`) to get back onto the Qt main thread safely.
- Pause is implemented with a `threading.Event`; pause time is tracked as "pause debt" subtracted from elapsed time so word-timing callbacks stay accurate.
- The `style: 0.0` voice setting is critical — without it, repeated paragraphs caused the narrator to sound increasingly agitated.
- RTF export is minimal (plain text wrapped in an RTF envelope, Georgia font). It is not a full Markdown→RTF converter; formatting is not preserved in the exported RTF.
