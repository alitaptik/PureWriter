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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def play(text: str, api_key: str, voice_id: str,
         on_done=None, on_word=None) -> None:
    stop()
    _stop_event.clear()
    _pause_event.set()

    def _run():
        try:
            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                "/with-timestamps",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_v3",
                      "output_format": "mp3_44100_128"},
                timeout=30,
            )
            resp.raise_for_status()

            if _stop_event.is_set():
                return

            data = resp.json()
            audio_chunks = [base64.b64decode(data["audio_base64"])]
            al = data.get("alignment") or data.get("normalized_alignment") or {}
            all_chars = al.get("characters", [])
            all_starts = al.get("character_start_times_seconds", [])
            all_ends = al.get("character_end_times_seconds", [])

            if _stop_event.is_set():
                return

            mp3_bytes = b"".join(audio_chunks)
            decoded = miniaudio.decode(
                mp3_bytes,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=_SAMPLE_RATE,
            )
            audio = np.frombuffer(decoded.samples, dtype=np.int16)

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

    global _thread
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
