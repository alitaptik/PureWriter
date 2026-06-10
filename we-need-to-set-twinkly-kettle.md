# PureWriter — Feature Plan

## Context

PureWriter is a PyQt6 distraction-free writing app with ElevenLabs TTS. Three improvements are needed:
1. **ElevenLabs voice tags** — allow `[tag:value]` pronunciation hints inside text that get passed correctly to the API.
2. **Rich-text export/import** — save and load `.rtf` or `.md` files (`.md` is already supported; add proper RTF round-trip).
3. **TTS stability fix** — narrator becomes "too emotional/agitated" after a paragraph repetition, likely due to accumulated voice settings without a `voice_settings` reset in the API call.

---

## Feature 1 — ElevenLabs Voice Tags

### Problem
ElevenLabs supports SSML-like pronunciation tags (e.g. `<phoneme>`, `<break>`) and its own `[voice: ...]` style tags. Currently the text is sent raw to the API; there is no UI affordance for inserting tags, and the model used (`eleven_turbo_v2_5`) may not honour all tag types.

### Implementation

**`tts.py`** — no code change needed for basic tags; ElevenLabs already accepts them in the `text` field. However, switch model to `eleven_multilingual_v2` (or keep turbo) and set `enable_ssml_parsing: true` in the request body if SSML tags are desired:

```python
json={
    "text": text,
    "model_id": "eleven_turbo_v2_5",
    "output_format": "mp3_44100_128",
    "enable_ssml_parsing": True,   # ← add this
}
```

**`main.py`** — add an "Insert Tag" submenu under **Edit** with common tags:
- Break: `<break time="500ms"/>`
- Emphasis: `<emphasis level="strong">…</emphasis>` (wraps selection)
- Phoneme: `<phoneme alphabet="ipa" ph="…">…</phoneme>`

Use `editor._editor.textCursor()` to insert at cursor or wrap selection.

**`highlighter.py`** — add a regex rule to colour SSML/ElevenLabs tags distinctly (e.g. teal `#56b6c2`) so authors can see them in the editor.

---

## Feature 2 — Export / Import (RTF + existing TXT/MD)

### Problem
Save/load only handles `.txt` / `.md` as raw UTF-8. The user wants rich-text (RTF) support for interoperability with Word, Apple Pages, etc.

### Implementation

**New file: `purewriter/rtf_io.py`**
Use Python's `striprtf` library (read) and a minimal hand-rolled RTF writer (write) — no heavy dependency needed for basic bold/italic/heading support:
- `load_rtf(path) -> str` — strip RTF markup, return plain markdown-ish text
- `save_rtf(path, plain_text: str)` — wrap plain text in minimal RTF envelope

Add `striprtf` to `requirements.txt`.

**`main.py`** changes:
- `_open_file()` (line ~518): add `*.rtf` to the file filter and call `rtf_io.load_rtf()` for `.rtf` files.
- `_save_as()` (line ~537): add `*.rtf` option; call `rtf_io.save_rtf()` for `.rtf` files.
- `_save()` (line ~530): detect current file extension and dispatch accordingly.

---

## Feature 3 — TTS Stability Fix (Emotion / Agitation)

### Problem
After a repeated paragraph the narrator sounds "too emotional and agitated" (character: Artsy). This is almost certainly caused by missing `voice_settings` in the API payload — ElevenLabs carries over latent emotional state across requests when `stability` and `similarity_boost` are not explicitly set, and the model may also be reading the repetition as an emotional cue.

### Fix

**`tts.py`** — add explicit `voice_settings` to every request body (lines 63–65):

```python
json={
    "text": text,
    "model_id": "eleven_turbo_v2_5",
    "output_format": "mp3_44100_128",
    "enable_ssml_parsing": True,
    "voice_settings": {
        "stability": 0.55,          # 0 = expressive, 1 = monotone; 0.55 is balanced
        "similarity_boost": 0.75,   # voice clone fidelity
        "style": 0.0,               # style exaggeration — set to 0 to kill agitation
        "use_speaker_boost": True,
    },
}
```

The key lever is `style: 0.0` — ElevenLabs uses this to dial style exaggeration. Setting it explicitly to 0 on every call prevents drift between paragraphs.

Optionally expose these sliders in a **Settings → Voice Settings** dialog (future, not in this plan).

---

## Files to Modify

| File | Change |
|---|---|
| `purewriter/tts.py` | Add `voice_settings` + `enable_ssml_parsing` to request body |
| `purewriter/main.py` | Insert Tag menu; RTF open/save dispatch |
| `purewriter/highlighter.py` | Add SSML/tag highlight rule |
| `purewriter/requirements.txt` | Add `striprtf` |
| `purewriter/rtf_io.py` | **New file** — RTF load/save helpers |

---

## Verification

1. **Voice tags**: Type `Hello <break time="1s"/> world` in editor, press Ctrl+R — confirm audible pause.
2. **RTF export**: Write a paragraph, File → Save As → `test.rtf`, open in Apple Pages — confirm text is readable.
3. **RTF import**: File → Open → `test.rtf` — confirm text appears correctly in editor.
4. **Stability fix**: Play the same paragraph twice in a row with voice "Artsy" — confirm second reading is calm, not agitated.
