import base64
import json
import threading
import time

import miniaudio
import numpy as np
import requests
import sounddevice as sd

_stop_event = threading.Event()
_pause_event = threading.Event()
_pause_event.set()  # not paused
_thread: threading.Thread | None = None

_SAMPLE_RATE = 44100

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
# `transport` selects the API path that yields character alignment (→ word
# highlighting):
#   - "rest_timestamps": POST /text-to-speech/{voice}/with-timestamps. JSON with
#     audio_base64 + alignment. Works for Turbo/v2 family, NOT eleven_v3.
#   - "dialogue_stream": POST /text-to-dialogue/stream/with-timestamps. HTTP
#     streaming of JSON blobs (audio_base64 + alignment), default model eleven_v3.
#     This is how v3 gets word highlighting (the REST /with-timestamps and the
#     WebSocket stream-input paths do not support v3).

MODELS = {
    "eleven_turbo_v2_5": {
        "label": "Turbo v2.5",
        "transport": "rest_timestamps",
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.75,
                           "style": 0.0, "use_speaker_boost": True},
    },
    "eleven_v3": {
        "label": "Eleven v3",
        "transport": "dialogue_stream",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8,
                           "style": 0.0, "use_speaker_boost": True},
    },
}
DEFAULT_MODEL = "eleven_turbo_v2_5"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _word_timings(chars, starts, ends) -> list[tuple]:
    """Convert char-level timings → list of (t_start, t_end, char_start, char_end)."""
    words = []
    in_word = False
    w_t0 = 0.0
    w_c0 = 0

    for i, ch in enumerate(chars):
        if ch.strip():
            if not in_word:
                in_word = True
                w_t0 = starts[i]
                w_c0 = i
        else:
            if in_word:
                words.append((w_t0, ends[i - 1], w_c0, i))
                in_word = False

    if in_word:
        words.append((w_t0, ends[-1], w_c0, len(chars)))

    return words


def _decode_mp3(mp3_bytes: bytes) -> np.ndarray:
    decoded = miniaudio.decode(
        mp3_bytes,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=_SAMPLE_RATE,
    )
    return np.frombuffer(decoded.samples, dtype=np.int16)


def _fetch_rest(base, api_key, body, with_timestamps):
    """REST fetch. Returns (audio_int16, chars, starts, ends). Highlighting only
    when with_timestamps is True (the plain endpoint returns raw mp3, no alignment)."""
    resp = requests.post(
        base + ("/with-timestamps" if with_timestamps else ""),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    if with_timestamps:
        data = resp.json()
        mp3_bytes = base64.b64decode(data["audio_base64"])
        al = data.get("alignment") or data.get("normalized_alignment") or {}
        return (_decode_mp3(mp3_bytes),
                al.get("characters", []),
                al.get("character_start_times_seconds", []),
                al.get("character_end_times_seconds", []))
    return _decode_mp3(resp.content), [], [], []


def _fetch_dialogue_stream(api_key, text, voice_id, model_id, voice_settings):
    """v3 path: POST /text-to-dialogue/stream/with-timestamps and aggregate the
    streamed JSON blobs into one (audio_int16, chars, starts, ends).

    The raw MP3 bytes are concatenated and decoded ONCE at the end (decoding each
    chunk separately adds per-chunk decoder padding → audible gaps/clicks at every
    boundary). Alignment times are absolute from stream start, so they are used
    as-is against the single continuous buffer."""
    body = {
        "inputs": [{"text": text, "voice_id": voice_id}],
        "model_id": model_id,
        "settings": {
            "stability": voice_settings.get("stability", 0.5),
            "use_speaker_boost": voice_settings.get("use_speaker_boost", True),
        },
    }
    mp3_parts: list[bytes] = []
    chars: list[str] = []
    starts: list[float] = []
    ends: list[float] = []

    with requests.post(
        "https://api.elevenlabs.io/v1/text-to-dialogue/stream/with-timestamps",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        stream=True,
        timeout=60,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if _stop_event.is_set():
                break
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            try:
                blob = json.loads(line)
            except ValueError:
                continue

            b64 = blob.get("audio_base64") or blob.get("audio")
            if b64:
                mp3_parts.append(base64.b64decode(b64))

            al = blob.get("alignment") or blob.get("normalized_alignment") or {}
            c = al.get("characters", [])
            s = al.get("character_start_times_seconds", [])
            e = al.get("character_end_times_seconds", [])
            if c and s and e:
                chars.extend(c)
                starts.extend(s)
                ends.extend(e)

    audio = (_decode_mp3(b"".join(mp3_parts)) if mp3_parts
             else np.zeros(0, dtype=np.int16))
    return audio, chars, starts, ends


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _refresh_output_device() -> None:
    """Re-read CoreAudio's current default output device so playback follows
    device changes (e.g. connecting Bluetooth headphones) without an app
    restart. PortAudio otherwise caches the device list from process start."""
    try:
        sd._terminate()
        sd._initialize()
    except Exception as e:
        print(f"Audio device refresh failed: {e}")


def play(text: str, api_key: str, voice_id: str,
         model_id: str = DEFAULT_MODEL,
         on_done=None, on_word=None) -> None:
    global _thread
    stop()
    # Let any in-flight playback thread unwind before re-initialising PortAudio.
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=1.0)
    _refresh_output_device()
    _stop_event.clear()
    _pause_event.set()

    caps = MODELS.get(model_id, MODELS[DEFAULT_MODEL])

    def _run():
        try:
            base = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            body = {
                "text": text,
                "model_id": model_id,
                "output_format": "mp3_44100_128",
                "enable_ssml_parsing": True,
                "voice_settings": caps["voice_settings"],
            }

            if caps["transport"] == "dialogue_stream":
                try:
                    audio, all_chars, all_starts, all_ends = _fetch_dialogue_stream(
                        api_key, text, voice_id, model_id, caps["voice_settings"])
                except Exception as e:
                    # Fall back to plain audio-only so v3 never regresses to silence.
                    print(f"v3 dialogue stream failed ({e}); plain audio fallback")
                    audio, all_chars, all_starts, all_ends = _fetch_rest(
                        base, api_key, body, with_timestamps=False)
            else:
                audio, all_chars, all_starts, all_ends = _fetch_rest(
                    base, api_key, body, with_timestamps=True)

            if _stop_event.is_set():
                return

            timings = []
            if all_chars and on_word:
                timings = _word_timings(all_chars, all_starts, all_ends)

            start_time = time.monotonic()
            pause_debt = 0.0
            word_idx = 0
            block = 2048

            with sd.OutputStream(samplerate=_SAMPLE_RATE, channels=1,
                                  dtype="int16") as stream:
                for i in range(0, len(audio), block):
                    if _stop_event.is_set():
                        return

                    # Pause support
                    if not _pause_event.is_set():
                        pause_start = time.monotonic()
                        _pause_event.wait()
                        pause_debt += time.monotonic() - pause_start
                        if _stop_event.is_set():
                            return

                    elapsed = time.monotonic() - start_time - pause_debt

                    while (word_idx < len(timings)
                           and timings[word_idx][0] <= elapsed):
                        if on_word:
                            _, _, cs, ce = timings[word_idx]
                            on_word(cs, ce)
                        word_idx += 1

                    frame = audio[i: i + block]
                    stream.write(frame.reshape(-1, 1))

        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            if on_word:
                on_word(-1, -1)
            if on_done:
                on_done()

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()


def stop() -> None:
    _stop_event.set()
    _pause_event.set()  # unblock any waiting pause


def toggle_pause() -> bool:
    """Toggle pause. Returns True if now paused."""
    if _pause_event.is_set():
        _pause_event.clear()
        return True
    else:
        _pause_event.set()
        return False


def is_paused() -> bool:
    return not _pause_event.is_set()
