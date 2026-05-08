import re

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QPainter, QTextCharFormat,
                          QTextCursor)
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from highlighter import MarkdownHighlighter

_TAG_RE = re.compile(r"\[[^\]]+\]")


class _Margin(QWidget):
    play_clicked = pyqtSignal(int)  # block number

    def __init__(self, editor: "Editor"):
        super().__init__(editor)
        self._editor = editor
        self._hover_block = -1
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        return QSize(self._editor.margin_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_margin(self)

    def mouseMoveEvent(self, event):
        block = self._editor.block_at_y(int(event.position().y()))
        if block != self._hover_block:
            self._hover_block = block
            self.update()

    def leaveEvent(self, event):
        self._hover_block = -1
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            block = self._editor.block_at_y(int(event.position().y()))
            if block >= 0:
                self.play_clicked.emit(block)


class Editor(QPlainTextEdit):
    play_paragraph = pyqtSignal(str)
    playing_state_changed = pyqtSignal(bool)  # True = playing, False = stopped

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_block = -1
        self._is_playing = False
        self._highlight_doc_offset = 0

        self._margin = _Margin(self)
        self._margin.play_clicked.connect(self._on_margin_click)

        font = QFont("Georgia", 16)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.document().setDocumentMargin(20)

        self._highlighter = MarkdownHighlighter(self.document())

        self.updateRequest.connect(self._update_margin)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self._update_margin_width()

    def set_theme(self, theme: str):
        self._highlighter.set_theme(theme)

    # ------------------------------------------------------------------
    # Margin geometry
    # ------------------------------------------------------------------

    def margin_width(self) -> int:
        return 28

    def _update_margin_width(self):
        self.setViewportMargins(self.margin_width(), 0, 0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._margin.setGeometry(
            QRect(cr.left(), cr.top(), self.margin_width(), cr.height()))

    def _update_margin(self, rect, dy):
        if dy:
            self._margin.scroll(0, dy)
        else:
            self._margin.update(0, rect.y(), self._margin.width(), rect.height())

    # ------------------------------------------------------------------
    # Margin painting
    # ------------------------------------------------------------------

    def paint_margin(self, margin: _Margin):
        painter = QPainter(margin)
        painter.fillRect(margin.rect(), QColor("#1e1e1e"))

        cursor_block = self.textCursor().block().blockNumber()
        hover_block = margin._hover_block

        block = self.firstVisibleBlock()
        while block.isValid():
            geo = self.blockBoundingGeometry(block).translated(
                self.contentOffset())
            if geo.top() > margin.rect().bottom():
                break

            bn = block.blockNumber()
            is_paragraph = bool(block.text().strip())

            if is_paragraph and (bn == cursor_block or bn == hover_block):
                is_playing = self._is_playing and bn == self._active_block
                label = "■" if is_playing else "▶"
                color = QColor("#e06c75") if is_playing else QColor("#61afef")
                painter.setPen(color)
                painter.setFont(QFont("Helvetica", 10))
                y = int(geo.top())
                h = int(geo.height())
                painter.drawText(
                    QRect(0, y, margin.width() - 4, h),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    label,
                )

            block = block.next()

        painter.end()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def block_at_y(self, y: int) -> int:
        block = self.firstVisibleBlock()
        while block.isValid():
            geo = self.blockBoundingGeometry(block).translated(
                self.contentOffset())
            if geo.top() <= y <= geo.bottom():
                return block.blockNumber() if block.text().strip() else -1
            if geo.top() > y:
                break
            block = block.next()
        return -1

    def _paragraph_for_block(self, block_number: int) -> tuple[str, int]:
        """Return (full_text, doc_offset) for the paragraph containing block_number."""
        doc = self.document()
        block = doc.findBlockByNumber(block_number)
        while block.previous().isValid() and block.previous().text().strip():
            block = block.previous()
        doc_offset = block.position()
        lines = []
        while block.isValid() and block.text().strip():
            lines.append(block.text())
            block = block.next()
        return " ".join(lines).strip(), doc_offset

    def _paragraph_from_cursor(self) -> tuple[str, int]:
        """Return (text_from_cursor, doc_offset_of_cursor) for Cmd+R play-from-here."""
        cursor = self.textCursor()
        doc = self.document()

        # Find paragraph start block
        block = cursor.block()
        while block.previous().isValid() and block.previous().text().strip():
            block = block.previous()
        para_start_offset = block.position()

        # Build full paragraph text to find cursor's char position within it
        lines = []
        b = block
        while b.isValid() and b.text().strip():
            lines.append(b.text())
            b = b.next()
        full_text = " ".join(lines).strip()

        # Cursor position within the paragraph
        cursor_in_para = cursor.position() - para_start_offset
        cursor_in_para = max(0, min(cursor_in_para, len(full_text)))

        # Trim to word boundary so we don't start mid-word
        while cursor_in_para > 0 and full_text[cursor_in_para - 1] not in (" ", "\n"):
            cursor_in_para -= 1

        text_from_cursor = full_text[cursor_in_para:].strip()
        doc_offset = para_start_offset + cursor_in_para
        return text_from_cursor, doc_offset

    # ------------------------------------------------------------------
    # Word highlighting (called from main thread via signal)
    # ------------------------------------------------------------------

    def highlight_word(self, char_start: int, char_end: int):
        if char_start < 0:
            self.setExtraSelections([])
            return

        # ElevenLabs strips [tags] before generating alignment, so char indices
        # from the API are relative to tag-stripped text. Map them back to the
        # original text positions so the highlight lands on the right word.
        doc = self.document()
        origin = self._highlight_doc_offset
        raw_text = doc.toPlainText()[origin: origin + char_end + 200]

        tag_offset = 0
        for m in _TAG_RE.finditer(raw_text):
            if m.start() - tag_offset <= char_start:
                tag_offset += len(m.group())
            else:
                break

        sel = QTextEdit.ExtraSelection()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#e5c07b"))
        fmt.setForeground(QColor("#282c34"))
        sel.format = fmt
        cursor = QTextCursor(doc)
        cursor.setPosition(origin + char_start + tag_offset)
        cursor.setPosition(origin + char_end + tag_offset,
                           QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = cursor
        self.setExtraSelections([sel])

    # ------------------------------------------------------------------
    # Play state
    # ------------------------------------------------------------------

    def _on_cursor_moved(self):
        self._margin.update()

    def _on_margin_click(self, block_number: int):
        if self._is_playing and block_number == self._active_block:
            self.request_stop()
        else:
            text, offset = self._paragraph_for_block(block_number)
            if text:
                self._active_block = block_number
                self._highlight_doc_offset = offset
                self._is_playing = True
                self._margin.update()
                self.playing_state_changed.emit(True)
                self.play_paragraph.emit(text)

    def on_playback_done(self):
        self._is_playing = False
        self._active_block = -1
        self.setExtraSelections([])
        self._margin.update()
        self.playing_state_changed.emit(False)

    def request_stop(self):
        self._is_playing = False
        self._active_block = -1
        self.setExtraSelections([])
        self._margin.update()
        self.playing_state_changed.emit(False)

    def toggle_play_current(self):
        if self._is_playing:
            self.request_stop()
            self.play_paragraph.emit("")
        else:
            text, doc_offset = self._paragraph_from_cursor()
            if not text:
                return
            cursor = self.textCursor()
            block = cursor.block()
            while block.previous().isValid() and block.previous().text().strip():
                block = block.previous()
            self._active_block = block.blockNumber()
            self._highlight_doc_offset = doc_offset
            self._is_playing = True
            self._margin.update()
            self.playing_state_changed.emit(True)
            self.play_paragraph.emit(text)
