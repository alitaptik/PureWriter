import requests


def fetch_voices(api_key: str) -> list[dict]:
    """Return list of {id, name} dicts from ElevenLabs /v2/voices (all pages)."""
    results = []
    params = {"page_size": 100}
    while True:
        resp = requests.get(
            "https://api.elevenlabs.io/v2/voices",
            headers={"xi-api-key": api_key},
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        for v in data.get("voices", []):
            results.append({"id": v["voice_id"], "name": v["name"]})
        token = data.get("next_page_token")
        if not token:
            break
        params["next_page_token"] = token
    return results
