from pathlib import Path

from striprtf.striprtf import rtf_to_text


def load_rtf(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return rtf_to_text(raw)


def save_rtf(path: Path, text: str) -> None:
    # Minimal RTF envelope: plain text, UTF-8 declared, newlines as \par
    escaped = (
        text
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )
    lines = escaped.splitlines()
    body = "\n\\par\n".join(lines)
    rtf = (
        "{\\rtf1\\ansi\\deff0\n"
        "{\\fonttbl{\\f0 Georgia;}}\n"
        "\\f0\\fs32\n"
        f"{body}\n"
        "}"
    )
    path.write_text(rtf, encoding="utf-8")
