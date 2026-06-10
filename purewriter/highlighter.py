import re

from PyQt6.QtGui import (QFont, QSyntaxHighlighter, QTextCharFormat,
                          QColor)


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme: str = "dark"):
        super().__init__(document)
        self._theme = theme
        self._build_rules()

    def set_theme(self, theme: str):
        self._theme = theme
        self._build_rules()
        self.rehighlight()

    def _c(self, dark_hex: str, light_hex: str) -> QColor:
        return QColor(dark_hex if self._theme == "dark" else light_hex)

    def _build_rules(self):
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []

        def fmt(color=None, bold=False, italic=False,
                size=None, mono=False, strike=False) -> QTextCharFormat:
            f = QTextCharFormat()
            if color:
                f.setForeground(color)
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            if italic:
                f.setFontItalic(True)
            if size:
                f.setFontPointSize(size)
            if mono:
                f.setFontFamilies(["Menlo", "Courier New", "monospace"])
            if strike:
                f.setFontStrikeOut(True)
            return f

        # H1
        self._rules.append((
            re.compile(r"^#{1}\s.+", re.MULTILINE),
            fmt(color=self._c("#e5c07b", "#333333"), bold=True, size=22),
        ))
        # H2
        self._rules.append((
            re.compile(r"^#{2}\s.+", re.MULTILINE),
            fmt(color=self._c("#e5c07b", "#333333"), bold=True, size=19),
        ))
        # H3–H6
        self._rules.append((
            re.compile(r"^#{3,6}\s.+", re.MULTILINE),
            fmt(color=self._c("#e5c07b", "#333333"), bold=True, size=17),
        ))
        # Bold **text** or __text__
        self._rules.append((
            re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__"),
            fmt(bold=True),
        ))
        # Italic *text* or _text_  (after bold so ** is already consumed)
        self._rules.append((
            re.compile(r"(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)"
                       r"|(?<!_)_(?!_)([^_\n]+)(?<!_)_(?!_)"),
            fmt(italic=True),
        ))
        # Strikethrough ~~text~~
        self._rules.append((
            re.compile(r"~~[^~\n]+~~"),
            fmt(color=self._c("#5c6370", "#999999"), strike=True),
        ))
        # Inline code `code`
        self._rules.append((
            re.compile(r"`[^`\n]+`"),
            fmt(color=self._c("#98c379", "#2d7a2d"), mono=True),
        ))
        # Blockquote > ...
        self._rules.append((
            re.compile(r"^>.*", re.MULTILINE),
            fmt(color=self._c("#5c6370", "#888888"), italic=True),
        ))
        # Link text [text](url)
        self._rules.append((
            re.compile(r"\[[^\]\n]*\]\([^\)\n]*\)"),
            fmt(color=self._c("#61afef", "#0057d8")),
        ))
        # Horizontal rule --- or ***
        self._rules.append((
            re.compile(r"^[-*]{3,}\s*$", re.MULTILINE),
            fmt(color=self._c("#3e4451", "#cccccc")),
        ))
        # Unordered list marker
        self._rules.append((
            re.compile(r"^(\s*[-*+])\s", re.MULTILINE),
            fmt(color=self._c("#e06c75", "#cc0000"), bold=True),
        ))
        # Ordered list marker
        self._rules.append((
            re.compile(r"^\s*\d+\.\s", re.MULTILINE),
            fmt(color=self._c("#e06c75", "#cc0000"), bold=True),
        ))
        # Fenced code block markers ```
        self._rules.append((
            re.compile(r"^```.*$", re.MULTILINE),
            fmt(color=self._c("#98c379", "#2d7a2d"), mono=True),
        ))
        # Markdown syntax markers: ** __ * _ ~~ ` # >
        # Dim them so they recede visually without disappearing
        self._rules.append((
            re.compile(r"\*\*|__|~~|(?<!\w)\*(?!\s)|(?<!\w)_(?!\s)"),
            fmt(color=self._c("#4b5263", "#bbbbbb")),
        ))
        # SSML / ElevenLabs tags  <break .../>, <emphasis ...>, </emphasis>, etc.
        self._rules.append((
            re.compile(r"</?[a-zA-Z][^>\n]*>"),
            fmt(color=self._c("#56b6c2", "#007a99")),
        ))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
