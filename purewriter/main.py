import sys
from pathlib import Path

import markdown as md_lib
from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QPalette, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import config
import rtf_io
import tts
import voices
from editor import Editor


# ---------------------------------------------------------------------------
# Thread-safe bridge: routes word callbacks from TTS thread → Qt main thread
# ---------------------------------------------------------------------------

class _WordBridge(QObject):
    word = pyqtSignal(int, int)


# ---------------------------------------------------------------------------
# Background worker for loading voices
# ---------------------------------------------------------------------------

class VoiceLoader(QThread):
    loaded = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_key: str):
        super().__init__()
        self._api_key = api_key

    def run(self):
        try:
            result = voices.fetch_voices(self._api_key)
            self.loaded.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# API key dialog
# ---------------------------------------------------------------------------

class ApiKeyDialog(QDialog):
    def __init__(self, current_key: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("ElevenLabs API Key")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter your ElevenLabs API key:"))

        self._field = QLineEdit(current_key)
        self._field.setEchoMode(QLineEdit.EchoMode.Password)
        self._field.setPlaceholderText("sk_...")
        layout.addWidget(self._field)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def key(self) -> str:
        return self._field.text().strip()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._cfg = config.load()
        self._voices: list[dict] = []
        self._current_file: Path | None = None
        self._word_bridge = _WordBridge()

        # Debounce timer for MD preview refresh
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self._build_ui()
        self._apply_theme(self._cfg.get("theme", "dark"))
        self._build_menu()

        self._word_bridge.word.connect(self._editor.highlight_word)
        self._editor.playing_state_changed.connect(self._on_playing_state)
        self._editor.textChanged.connect(self._on_text_changed)

        self.resize(self._cfg.get("window_width", 900),
                    self._cfg.get("window_height", 700))

        if self._cfg.get("preview_visible"):
            self._set_preview_visible(True)

        if not self._cfg.get("api_key"):
            self._prompt_api_key(first_launch=True)
        else:
            self._load_voices()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Top toolbar: voice selector
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setFloatable(False)

        lbl = QLabel("Voice: ")
        lbl.setContentsMargins(8, 0, 4, 0)
        toolbar.addWidget(lbl)

        self._voice_combo = QComboBox()
        self._voice_combo.setMinimumWidth(200)
        self._voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        toolbar.addWidget(self._voice_combo)

        self.addToolBar(toolbar)

        # Splitter: editor left, MD preview right
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        self._editor = Editor()
        self._editor.play_paragraph.connect(self._on_play_paragraph)
        self._splitter.addWidget(self._editor)

        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(True)
        self._preview.hide()
        self._splitter.addWidget(self._preview)

        vbox.addWidget(self._splitter)

        # Player bar (bottom)
        vbox.addWidget(self._build_player_bar())

    def _build_player_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("playerBar")
        bar.setFixedHeight(42)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self._btn_play = QPushButton("▶")
        self._btn_play.setObjectName("playerBtn")
        self._btn_play.setFixedSize(32, 32)
        self._btn_play.setToolTip("Play current paragraph  (Cmd+R)")
        self._btn_play.clicked.connect(self._editor.toggle_play_current)

        self._btn_pause = QPushButton("⏸")
        self._btn_pause.setObjectName("playerBtn")
        self._btn_pause.setFixedSize(32, 32)
        self._btn_pause.setToolTip("Pause / Resume")
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self._on_pause_clicked)

        self._btn_stop = QPushButton("⏹")
        self._btn_stop.setObjectName("playerBtn")
        self._btn_stop.setFixedSize(32, 32)
        self._btn_stop.setToolTip("Stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop_clicked)

        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("playerStatus")

        self._char_label = QLabel("0 chars")
        self._char_label.setObjectName("playerStatus")
        self._char_label.setToolTip("Characters sent to ElevenLabs this session")
        self._session_chars = 0

        layout.addWidget(self._btn_play)
        layout.addWidget(self._btn_pause)
        layout.addWidget(self._btn_stop)
        layout.addSpacing(8)
        layout.addWidget(self._status_label, stretch=1)
        layout.addWidget(self._char_label)

        return bar

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    _THEMES = {
        "dark": {
            "palette": {
                "window":   "#1e1e1e",
                "windowText": "#abb2bf",
                "base":     "#282c34",
                "text":     "#abb2bf",
                "button":   "#1e1e1e",
                "buttonText": "#abb2bf",
            },
            "css": """
                QPlainTextEdit {
                    background: #282c34; color: #abb2bf; border: none;
                    selection-background-color: #3e4451;
                }
                QTextBrowser {
                    background: #282c34; color: #abb2bf; border: none;
                    padding: 20px;
                }
                QToolBar { background: #21252b; border-bottom: 1px solid #181a1f; padding: 4px; }
                QSplitter::handle { background: #181a1f; width: 1px; }
                QComboBox {
                    background: #2c313a; color: #abb2bf;
                    border: 1px solid #3e4451; padding: 2px 6px; border-radius: 3px;
                }
                QComboBox QAbstractItemView { background: #2c313a; color: #abb2bf; selection-background-color: #3e4451; }
                QLabel { color: #abb2bf; }
                QMenuBar { background: #21252b; color: #abb2bf; }
                QMenuBar::item:selected { background: #3e4451; }
                QMenu { background: #21252b; color: #abb2bf; border: 1px solid #3e4451; }
                QMenu::item:selected { background: #3e4451; }
                QWidget#playerBar { background: #21252b; border-top: 1px solid #181a1f; }
                QPushButton#playerBtn {
                    background: #2c313a; color: #abb2bf;
                    border: 1px solid #3e4451; border-radius: 4px; font-size: 14px;
                }
                QPushButton#playerBtn:hover { background: #3e4451; }
                QPushButton#playerBtn:pressed { background: #4b5263; }
                QPushButton#playerBtn:disabled { color: #4b5263; border-color: #2c313a; }
                QLabel#playerStatus { color: #5c6370; font-size: 12px; }
            """,
            "preview_css": """
                body { font-family: Georgia, serif; font-size: 16px;
                       color: #abb2bf; background: #282c34;
                       max-width: 680px; margin: 0 auto; line-height: 1.7; }
                h1,h2,h3 { color: #e5c07b; }
                a { color: #61afef; }
                code { background: #2c313a; padding: 2px 5px; border-radius: 3px; }
                blockquote { border-left: 3px solid #3e4451; margin-left: 0; padding-left: 16px; color: #5c6370; }
            """,
        },
        "light": {
            "palette": {
                "window":   "#f7f7f5",
                "windowText": "#1a1a1a",
                "base":     "#ffffff",
                "text":     "#1a1a1a",
                "button":   "#f7f7f5",
                "buttonText": "#1a1a1a",
            },
            "css": """
                QPlainTextEdit {
                    background: #ffffff; color: #1a1a1a; border: none;
                    selection-background-color: #b3d4ff;
                }
                QTextBrowser {
                    background: #ffffff; color: #1a1a1a; border: none;
                    padding: 20px;
                }
                QToolBar { background: #f0f0ee; border-bottom: 1px solid #ddd; padding: 4px; }
                QSplitter::handle { background: #ddd; width: 1px; }
                QComboBox {
                    background: #ffffff; color: #1a1a1a;
                    border: 1px solid #ccc; padding: 2px 6px; border-radius: 3px;
                }
                QComboBox QAbstractItemView { background: #ffffff; color: #1a1a1a; selection-background-color: #b3d4ff; }
                QLabel { color: #1a1a1a; }
                QMenuBar { background: #f0f0ee; color: #1a1a1a; }
                QMenuBar::item:selected { background: #ddd; }
                QMenu { background: #ffffff; color: #1a1a1a; border: 1px solid #ccc; }
                QMenu::item:selected { background: #b3d4ff; }
                QWidget#playerBar { background: #f0f0ee; border-top: 1px solid #ddd; }
                QPushButton#playerBtn {
                    background: #ffffff; color: #1a1a1a;
                    border: 1px solid #ccc; border-radius: 4px; font-size: 14px;
                }
                QPushButton#playerBtn:hover { background: #e8e8e8; }
                QPushButton#playerBtn:pressed { background: #d0d0d0; }
                QPushButton#playerBtn:disabled { color: #bbb; border-color: #e0e0e0; }
                QLabel#playerStatus { color: #888; font-size: 12px; }
            """,
            "preview_css": """
                body { font-family: Georgia, serif; font-size: 16px;
                       color: #1a1a1a; background: #ffffff;
                       max-width: 680px; margin: 0 auto; line-height: 1.7; }
                h1,h2,h3 { color: #333; }
                a { color: #0057d8; }
                code { background: #f4f4f4; padding: 2px 5px; border-radius: 3px; }
                blockquote { border-left: 3px solid #ccc; margin-left: 0; padding-left: 16px; color: #666; }
            """,
        },
    }

    def _apply_theme(self, theme: str):
        t = self._THEMES.get(theme, self._THEMES["dark"])
        p = t["palette"]

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window,      QColor(p["window"]))
        palette.setColor(QPalette.ColorRole.WindowText,  QColor(p["windowText"]))
        palette.setColor(QPalette.ColorRole.Base,        QColor(p["base"]))
        palette.setColor(QPalette.ColorRole.Text,        QColor(p["text"]))
        palette.setColor(QPalette.ColorRole.Button,      QColor(p["button"]))
        palette.setColor(QPalette.ColorRole.ButtonText,  QColor(p["buttonText"]))
        QApplication.instance().setPalette(palette)

        self.setStyleSheet(t["css"])
        self._cfg["theme"] = theme
        config.save(self._cfg)
        self._editor.set_theme(theme)
        self._refresh_preview()

    def _toggle_theme(self):
        current = self._cfg.get("theme", "dark")
        self._apply_theme("light" if current == "dark" else "dark")

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        self._add_action(file_menu, "New", "Ctrl+N", self._new_file)
        self._add_action(file_menu, "Open…", "Ctrl+O", self._open_file)
        self._add_action(file_menu, "Save", "Ctrl+S", self._save_file)
        self._add_action(file_menu, "Save As…", "Ctrl+Shift+S", self._save_file_as)

        view_menu = menubar.addMenu("View")
        self._add_action(view_menu, "Toggle Light / Dark", "Ctrl+Shift+T", self._toggle_theme)
        view_menu.addSeparator()
        self._add_action(view_menu, "Toggle MD Preview", "Ctrl+Shift+P", self._toggle_preview)

        edit_menu = menubar.addMenu("Edit")
        play_action = QAction("Play / Stop Paragraph", self)
        play_action.setShortcut(QKeySequence("Ctrl+R"))
        play_action.triggered.connect(self._editor.toggle_play_current)
        edit_menu.addAction(play_action)

        edit_menu.addSeparator()
        tag_menu = edit_menu.addMenu("Insert Tag")
        self._add_action(tag_menu, "Break (0.5 s)", "", lambda: self._insert_tag('<break time="500ms"/>'))
        self._add_action(tag_menu, "Break (1 s)",   "", lambda: self._insert_tag('<break time="1s"/>'))
        self._add_action(tag_menu, "Emphasis (wrap selection)", "", lambda: self._wrap_tag('<emphasis level="strong">', "</emphasis>"))
        self._add_action(tag_menu, "Phoneme (wrap selection)",  "", lambda: self._wrap_tag('<phoneme alphabet="ipa" ph="">', "</phoneme>"))

        settings_menu = menubar.addMenu("Settings")
        self._add_action(settings_menu, "Update API Key…", "", self._prompt_api_key)

    def _add_action(self, menu, label, shortcut, slot):
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)

    # ------------------------------------------------------------------
    # MD preview
    # ------------------------------------------------------------------

    def _toggle_preview(self):
        self._set_preview_visible(self._preview.isHidden())

    def _set_preview_visible(self, visible: bool):
        self._preview.setVisible(visible)
        if visible:
            total = self._splitter.width()
            self._splitter.setSizes([total // 2, total // 2])
            self._refresh_preview()
        self._cfg["preview_visible"] = visible
        config.save(self._cfg)

    def _on_text_changed(self):
        if self._preview.isVisible():
            self._preview_timer.start()

    def _refresh_preview(self):
        if not self._preview.isVisible():
            return
        raw = self._editor.toPlainText()
        theme = self._cfg.get("theme", "dark")
        preview_css = self._THEMES.get(theme, self._THEMES["dark"])["preview_css"]
        body = md_lib.markdown(raw, extensions=["fenced_code", "tables"])
        html = f"<html><head><style>{preview_css}</style></head><body>{body}</body></html>"
        # Preserve scroll position
        sb = self._preview.verticalScrollBar()
        pos = sb.value()
        self._preview.setHtml(html)
        sb.setValue(pos)

    # ------------------------------------------------------------------
    # Player bar slots
    # ------------------------------------------------------------------

    def _on_playing_state(self, playing: bool):
        self._btn_play.setEnabled(not playing)
        self._btn_pause.setEnabled(playing)
        self._btn_stop.setEnabled(playing)
        self._btn_pause.setText("⏸")
        if not playing:
            self._status_label.setText("Ready")

    def _on_pause_clicked(self):
        paused = tts.toggle_pause()
        self._btn_pause.setText("▶" if paused else "⏸")
        self._status_label.setText("Paused" if paused else "Playing…")

    def _on_stop_clicked(self):
        tts.stop()
        self._editor.on_playback_done()

    # ------------------------------------------------------------------
    # Voice management
    # ------------------------------------------------------------------

    def _load_voices(self):
        self._voice_combo.clear()
        self._voice_combo.addItem("Loading voices…")
        self._voice_combo.setEnabled(False)

        self._loader = VoiceLoader(self._cfg["api_key"])
        self._loader.loaded.connect(self._on_voices_loaded)
        self._loader.error.connect(self._on_voices_error)
        self._loader.start()

    def _on_voices_loaded(self, voice_list: list):
        self._voices = voice_list
        self._voice_combo.clear()
        for v in voice_list:
            self._voice_combo.addItem(v["name"], v["id"])

        last = self._cfg.get("last_voice_id", "")
        if last:
            for i, v in enumerate(voice_list):
                if v["id"] == last:
                    self._voice_combo.setCurrentIndex(i)
                    break

        self._voice_combo.setEnabled(True)

    def _on_voices_error(self, msg: str):
        self._voice_combo.clear()
        self._voice_combo.addItem("Failed to load voices")
        QMessageBox.warning(self, "Voice Load Error",
                            f"Could not fetch voices:\n{msg}")

    def _on_voice_changed(self):
        idx = self._voice_combo.currentIndex()
        if idx >= 0 and self._voice_combo.isEnabled():
            voice_id = self._voice_combo.itemData(idx)
            if voice_id:
                self._cfg["last_voice_id"] = voice_id
                config.save(self._cfg)

    def _current_voice_id(self) -> str:
        idx = self._voice_combo.currentIndex()
        if idx >= 0:
            return self._voice_combo.itemData(idx) or ""
        return ""

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------

    def _on_play_paragraph(self, text: str):
        if not text:
            tts.stop()
            self._editor.on_playback_done()
            return

        api_key = self._cfg.get("api_key", "")
        voice_id = self._current_voice_id()

        if not api_key:
            QMessageBox.warning(self, "No API Key",
                                "Please set your ElevenLabs API key in Settings.")
            self._editor.on_playback_done()
            return

        if not voice_id:
            QMessageBox.warning(self, "No Voice", "Please select a voice.")
            self._editor.on_playback_done()
            return

        preview = text[:60] + ("…" if len(text) > 60 else "")
        self._status_label.setText(f"Playing: {preview}")
        self._session_chars += len(text)
        self._char_label.setText(f"{self._session_chars:,} chars")

        tts.play(
            text, api_key, voice_id,
            on_done=self._editor.on_playback_done,
            on_word=self._word_bridge.word.emit,
        )

    # ------------------------------------------------------------------
    # Tag insertion helpers
    # ------------------------------------------------------------------

    def _insert_tag(self, tag: str):
        cursor = self._editor.textCursor()
        cursor.insertText(tag)
        self._editor.setTextCursor(cursor)

    def _wrap_tag(self, open_tag: str, close_tag: str):
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            cursor.insertText(f"{open_tag}{selected}{close_tag}")
        else:
            cursor.insertText(f"{open_tag}{close_tag}")
            cursor.movePosition(cursor.MoveOperation.Left, cursor.MoveMode.MoveAnchor, len(close_tag))
            self._editor.setTextCursor(cursor)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _new_file(self):
        self._editor.clear()
        self._current_file = None
        self.setWindowTitle("PureWriter — Untitled")

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "",
            "All Supported (*.txt *.md *.rtf);;Text / Markdown (*.txt *.md);;Rich Text (*.rtf);;All Files (*)"
        )
        if path:
            self._load_path(Path(path))

    def _load_path(self, path: Path):
        if path.suffix.lower() == ".rtf":
            text = rtf_io.load_rtf(path)
        else:
            text = path.read_text(encoding="utf-8")
        self._editor.setPlainText(text)
        self._current_file = path
        self.setWindowTitle(f"PureWriter — {path.name}")

    def _save_file(self):
        if self._current_file:
            self._write(self._current_file)
        else:
            self._save_file_as()

    def _save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save File", "",
            "Markdown (*.md);;Plain Text (*.txt);;Rich Text (*.rtf);;All Files (*)"
        )
        if path:
            p = Path(path)
            self._write(p)
            self._current_file = p
            self.setWindowTitle(f"PureWriter — {p.name}")

    def _write(self, path: Path):
        if path.suffix.lower() == ".rtf":
            rtf_io.save_rtf(path, self._editor.toPlainText())
        else:
            path.write_text(self._editor.toPlainText(), encoding="utf-8")

    # ------------------------------------------------------------------
    # API key
    # ------------------------------------------------------------------

    def _prompt_api_key(self, first_launch: bool = False):
        dlg = ApiKeyDialog(self._cfg.get("api_key", ""), self)
        if first_launch:
            dlg.setWindowTitle("Welcome to PureWriter — Set API Key")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            key = dlg.key()
            if key:
                self._cfg["api_key"] = key
                config.save(self._cfg)
                self._load_voices()

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        tts.stop()
        self._cfg["window_width"] = self.width()
        self._cfg["window_height"] = self.height()
        config.save(self._cfg)
        super().closeEvent(event)


# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PureWriter")
    win = MainWindow()
    win.setWindowTitle("PureWriter — Untitled")
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
