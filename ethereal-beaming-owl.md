# Plan: Model switcher + Eleven v3 support

## Context

PureWriter currently hardcodes the ElevenLabs model to `eleven_turbo_v2_5` in
[tts.py:65](purewriter/tts.py#L65). The user wants a UI model switcher offering
**Turbo v2.5** (current) and **Eleven v3**.

Research (June 2026) confirms:
- **Eleven v3 is generally available** (GA since 2026-03-14, no longer alpha).
- v3 adds *audio tags* like `[whispers]`, `[excited]`, `[sighs]` and is the most
  expressive model; ElevenLabs still recommends Turbo/Flash for low latency.
- **Crucial limitation:** the standard REST endpoint
  `POST /v1/text-to-speech/{voice_id}/with-timestamps` does **not** reliably return
  character alignment for v3. v3 character timing is only available via the
  WebSocket / text-to-dialogue streaming endpoints. PureWriter's word-highlighting
  ([editor.py highlight_word], driven by alignment in [tts.py:84-131](purewriter/tts.py#L84-L131))
  therefore cannot work with v3 over the current transport.

**Decision:** v3 uses the plain `POST /v1/text-to-speech/{voice_id}` endpoint
(raw mp3, no alignment) and auto-disables word highlighting. Turbo v2.5 keeps the
existing `/with-timestamps` path with full highlighting and SSML. (Full v3
highlighting via WebSocket is possible but out of scope — noted as future work.)

## Changes

### `purewriter/tts.py`
1. Add a module-level capability table:
   ```python
   MODELS = {
       "eleven_turbo_v2_5": {
           "label": "Turbo v2.5",
           "timestamps": True,
           "voice_settings": {"stability": 0.55, "similarity_boost": 0.75,
                              "style": 0.0, "use_speaker_boost": True},
       },
       "eleven_v3": {
           "label": "Eleven v3",
           "timestamps": False,
           "voice_settings": {"stability": 0.5, "similarity_boost": 0.8,
                              "style": 0.0, "use_speaker_boost": True},
       },
   }
   DEFAULT_MODEL = "eleven_turbo_v2_5"
   ```
2. Add a `model_id: str = DEFAULT_MODEL` parameter to `play()`. Look up
   `caps = MODELS.get(model_id, MODELS[DEFAULT_MODEL])` and use
   `caps["voice_settings"]` in the request body.
3. Split the fetch into two paths based on `caps["timestamps"]`:
   - **True** → existing `/with-timestamps` request; parse JSON, base64-decode
     `audio_base64`, build `timings` from alignment (current code at
     [tts.py:82-103](purewriter/tts.py#L82-L103)).
   - **False** → `POST /v1/text-to-speech/{voice_id}` (same headers/body minus
     timestamp handling); response body is raw mp3 bytes; `timings = []`.
   Keep `enable_ssml_parsing: True` for both (harmless for v3, needed for Turbo).
4. Factor the shared decode + playback loop ([tts.py:92-134](purewriter/tts.py#L92-L134))
   so both paths feed `(mp3_bytes, timings)` into it. The existing
   `if all_chars and on_word` / empty-`timings` guards already make the playback loop
   a no-op for highlighting when there is no alignment — so audio-only v3 works with
   no further branching inside the loop.

### `purewriter/config.py`
- Add `"last_model_id": "eleven_turbo_v2_5"` to `DEFAULTS`
  ([config.py:8-15](purewriter/config.py#L8-L15)).

### `purewriter/main.py`
- Add a model `QComboBox` to the toolbar next to the voice combo
  ([main.py:147-150](purewriter/main.py#L147-L150)). Populate from `tts.MODELS`
  (label shown, `model_id` as item data). Restore `last_model_id` from config on
  startup; default to `eleven_turbo_v2_5`.
- Add `_on_model_changed()` (mirrors `_on_voice_changed` at
  [main.py:473-479](purewriter/main.py#L473-L479)) to persist `last_model_id`.
- Add `_current_model_id()` helper (mirrors `_current_voice_id` at
  [main.py:481-484](purewriter/main.py#L481-L484)).
- Pass `model_id=self._current_model_id()` into the `tts.play(...)` call at
  [main.py:517](purewriter/main.py#L517).
- Apply the existing dark/light `QComboBox` styles ([main.py:241-245](purewriter/main.py#L241-L245),
  [main.py:291-295](purewriter/main.py#L291-L295)) to the new combo (they target all
  `QComboBox` already, so no extra CSS needed).

### `CLAUDE.md`
- Update the "ElevenLabs API details" section: model is now selectable
  (Turbo v2.5 / Eleven v3); note v3 uses the plain endpoint with no word
  highlighting and uses audio tags `[...]`; add `last_model_id` to the config keys list.

## Out of scope (noted for the user)
- v3 word highlighting (needs WebSocket/dialogue streaming transport).
- A v3-specific "Insert Audio Tag" menu (`[whispers]`, `[excited]`, …) and a
  highlighter rule for `[...]` tags — could be a fast follow if desired.

## Verification
1. `pip install -r purewriter/requirements.txt` (no new deps), then
   `python purewriter/main.py`.
2. Toolbar shows a **Model** dropdown with "Turbo v2.5" and "Eleven v3".
3. Select **Turbo v2.5**, type `Hello <break time="1s"/> world`, press Ctrl+R →
   audible pause **and** words highlight in sync.
4. Select **Eleven v3**, type `[whispers] this is a secret [excited] surprise!`,
   press Ctrl+R → expressive v3 audio plays; no word highlighting (expected); no error.
5. Restart the app → the last-selected model is restored from
   `~/.purewriter/config.json` (`last_model_id`).

## Sources
- ElevenLabs Models — https://elevenlabs.io/docs/overview/models
- Create speech with timing — https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
- v3 Audio Tags — https://elevenlabs.io/blog/v3-audiotags
- ElevenLabs Cheat Sheet 2026 — https://www.webfuse.com/elevenlabs-cheat-sheet
