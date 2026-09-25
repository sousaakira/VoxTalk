"""Janela principal do VoxTalk (PyQt5)."""

from __future__ import annotations

import threading
from typing import Optional

import pyperclip
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMenu,
    QAction,
    QProgressBar,
)

from .bubble import RecordingBubble
from . import gnome_shortcut
from .ipc import InstanceServer, default_socket_path, send_command
from .model_manager import ensure_parakeet, model_ready
from .recorder import MicrophoneRecorder
from .settings import AppSettings, load_settings, save_settings
from .settings_dialog import SettingsDialog
from .text_injector import InjectionUnavailable, TextInjector
from .transcriber import ENGINE_LABELS, LANGUAGES, HybridTranscriber


class WorkerBus(QObject):
    """Sinais thread-safe para a UI (sempre entregues na thread do Qt)."""

    status = pyqtSignal(str)
    transcript = pyqtSignal(str, str)  # text, language
    error = pyqtSignal(str)
    recording_level = pyqtSignal(float)
    hotkey_toggle = pyqtSignal()  # pynput / socket → thread principal
    show_window = pyqtSignal()
    injected = pyqtSignal(bool, str)  # ok, mensagem



def _mic_icon(recording: bool = False) -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    color = QColor("#e74c3c") if recording else QColor("#2ecc71")
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawEllipse(18, 8, 28, 36)
    p.drawRect(28, 40, 8, 10)
    p.drawRoundedRect(16, 48, 32, 8, 3, 3)
    p.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VoxTalk")
        self.setMinimumSize(520, 420)
        self.resize(640, 520)

        self.recorder = MicrophoneRecorder()
        self.transcriber = HybridTranscriber()
        self.settings: AppSettings = load_settings()
        self.bus = WorkerBus(self)  # afinidade = thread da UI
        self._hotkey = None  # GlobalHotkey (pynput), só fora do GNOME
        self._pynput_label = ""
        self._injector = TextInjector()
        self._inject_warned = False
        self._busy = False
        self._preparing_model = False

        self._build_ui()
        self._wire_signals()
        self._setup_tray()
        self._setup_bubble()
        self._apply_theme()

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(80)
        self._level_timer.timeout.connect(self._poll_level)

        self._bubble_hide_timer = QTimer(self)
        self._bubble_hide_timer.setSingleShot(True)
        self._bubble_hide_timer.timeout.connect(self.bubble.fade_out)

        self._setup_global_shortcut()
        self._apply_settings_to_ui()
        self._emit_ready_status()

        QTimer.singleShot(400, self._maybe_prompt_model_download)

    def _on_hotkey_from_listener(self) -> None:
        """Callback do pynput (thread estranha) → sinal Qt na UI."""
        self.bus.hotkey_toggle.emit()

    def on_external_command(self, command: str) -> None:
        """Comandos do socket (thread estranha) → sinais Qt na UI."""
        if command == "toggle":
            self.bus.hotkey_toggle.emit()
        elif command == "show":
            self.bus.show_window.emit()

    def _shortcut_label(self) -> str:
        if gnome_shortcut.is_gnome():
            return self.settings.shortcut if self.settings.gnome_shortcut else "desativado"
        return self._pynput_label or "indisponível"

    def _setup_global_shortcut(self) -> None:
        """GNOME (inclusive Wayland): atalho personalizado → `voxtalk --toggle`.
        Outros ambientes X11: pynput."""
        if gnome_shortcut.is_gnome():
            try:
                if self.settings.gnome_shortcut:
                    gnome_shortcut.register(
                        self.settings.shortcut, gnome_shortcut.toggle_command()
                    )
                else:
                    gnome_shortcut.unregister()
            except Exception as exc:
                self.bus.status.emit(f"Não foi possível registrar o atalho no GNOME: {exc}")
            return
        if self._hotkey is not None:
            return
        try:
            from .hotkey import GlobalHotkey, hotkey_label
        except Exception:
            self.bus.status.emit("Atalho global indisponível (pynput não instalado).")
            return
        # pynput roda em outra thread — NUNCA chamar Qt direto dali
        self._hotkey = GlobalHotkey(on_trigger=self._on_hotkey_from_listener)
        self._hotkey.start()
        self._pynput_label = hotkey_label()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("VoxTalk")
        title.setObjectName("brand")
        layout.addWidget(title)

        subtitle = QLabel(
            "Atalho global — pressione para gravar, de novo para transcrever."
        )
        self.subtitle = subtitle
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Motor:"))
        self.engine_label = QLabel("")
        self.engine_label.setObjectName("subtitle")
        engine_row.addWidget(self.engine_label, stretch=1)
        self.settings_btn = QPushButton("Configurações…")
        self.settings_btn.clicked.connect(self.open_settings)
        engine_row.addWidget(self.settings_btn)
        layout.addLayout(engine_row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Idioma:"))
        self.lang_combo = QComboBox()
        for code, label in LANGUAGES.items():
            self.lang_combo.addItem(label, code)
        self.lang_combo.currentIndexChanged.connect(self._persist_ui_prefs)
        row.addWidget(self.lang_combo, stretch=1)

        self.auto_copy = QCheckBox("Copiar automaticamente")
        self.auto_copy.toggled.connect(self._persist_ui_prefs)
        row.addWidget(self.auto_copy)
        layout.addLayout(row)

        self.status_label = QLabel("Pronto.")
        self.status_label.setObjectName("status")
        layout.addWidget(self.status_label)

        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(8)
        layout.addWidget(self.level_bar)

        self.text = QTextEdit()
        self.text.setPlaceholderText("O texto transcrito aparece aqui…")
        self.text.setFont(QFont("Ubuntu", 12))
        layout.addWidget(self.text, stretch=1)

        buttons = QHBoxLayout()
        self.record_btn = QPushButton("●  Gravar")
        self.record_btn.setObjectName("record")
        self.record_btn.clicked.connect(self.toggle_recording)
        buttons.addWidget(self.record_btn)

        copy_btn = QPushButton("Copiar")
        copy_btn.clicked.connect(self.copy_text)
        buttons.addWidget(copy_btn)

        clear_btn = QPushButton("Limpar")
        clear_btn.clicked.connect(self.text.clear)
        buttons.addWidget(clear_btn)
        layout.addLayout(buttons)

        tip = QLabel(
            "Dica: o atalho funciona minimizado. Padrão = Parakeet local (Orca). "
            "Em Configurações pode mudar para nuvem OpenAI."
        )
        tip.setObjectName("tip")
        tip.setWordWrap(True)
        layout.addWidget(tip)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #0f1419;
                color: #e7ecf1;
            }
            QLabel#brand {
                font-size: 28px;
                font-weight: 700;
                color: #5eead4;
                letter-spacing: 0.5px;
            }
            QLabel#subtitle, QLabel#tip {
                color: #94a3b8;
                font-size: 12px;
            }
            QLabel#status {
                color: #cbd5e1;
                font-size: 13px;
            }
            QTextEdit {
                background: #1a2332;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
                color: #f1f5f9;
                selection-background-color: #0d9488;
            }
            QComboBox, QPushButton {
                background: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px 14px;
                color: #f8fafc;
            }
            QPushButton:hover { background: #334155; }
            QPushButton#record {
                background: #0f766e;
                border-color: #14b8a6;
                font-weight: 600;
            }
            QPushButton#record[recording="true"] {
                background: #b91c1c;
                border-color: #ef4444;
            }
            QProgressBar {
                background: #1e293b;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: #14b8a6;
                border-radius: 4px;
            }
            QCheckBox { spacing: 8px; }
            """
        )

    def _setup_bubble(self) -> None:
        self.bubble = RecordingBubble()
        self.bubble.stop_requested.connect(self.toggle_recording)
        self.bubble.copy_requested.connect(self._copy_from_bubble)

    def _wire_signals(self) -> None:
        self.bus.status.connect(self.status_label.setText, Qt.QueuedConnection)
        self.bus.transcript.connect(self._on_transcript, Qt.QueuedConnection)
        self.bus.error.connect(self._on_error, Qt.QueuedConnection)
        self.bus.recording_level.connect(self._on_level, Qt.QueuedConnection)
        # pynput → UI: nunca mexer em widgets/timers fora desta thread
        self.bus.hotkey_toggle.connect(
            self.toggle_recording, Qt.QueuedConnection
        )
        self.bus.show_window.connect(self._show_from_tray, Qt.QueuedConnection)
        self.bus.injected.connect(self._on_injected, Qt.QueuedConnection)

    def _on_level(self, value: float) -> None:
        self.level_bar.setValue(int(value * 100))
        if self.recorder.is_recording:
            self.bubble.set_level(value)

    def _copy_from_bubble(self, text: str) -> None:
        try:
            pyperclip.copy(text)
            self.bus.status.emit("Texto copiado pelo balão.")
        except Exception as exc:
            self.bus.error.emit(f"Não foi possível copiar: {exc}")

    def _apply_settings_to_ui(self) -> None:
        idx = self.lang_combo.findData(self.settings.language)
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.lang_combo.blockSignals(False)
        self.auto_copy.blockSignals(True)
        self.auto_copy.setChecked(self.settings.auto_copy)
        self.auto_copy.blockSignals(False)
        self.engine_label.setText(ENGINE_LABELS.get(self.settings.engine, self.settings.engine))
        self.subtitle.setText(
            f"Atalho global: {self._shortcut_label()} — pressione para gravar, "
            "de novo para transcrever."
        )

    def _emit_ready_status(self) -> None:
        engine = ENGINE_LABELS.get(self.settings.engine, self.settings.engine)
        if self.settings.engine == "local":
            if model_ready(self.settings):
                self.bus.status.emit(f"Pronto ({engine}). Atalho: {self._shortcut_label()}")
            else:
                self.bus.status.emit(
                    f"Motor local sem modelo — abra Configurações para baixar (~670 MB). "
                    f"Atalho: {self._shortcut_label()}"
                )
        else:
            self.bus.status.emit(
                f"Pronto ({engine}). Precisa de internet + chave OpenAI. "
                f"Atalho: {self._shortcut_label()}"
            )

    def _persist_ui_prefs(self) -> None:
        self.settings.language = self.lang_combo.currentData() or "pt-BR"
        self.settings.auto_copy = self.auto_copy.isChecked()
        save_settings(self.settings)

    def open_settings(self) -> None:
        dlg = SettingsDialog(
            self.settings,
            self,
            on_unload_local=self.transcriber.unload_local,
        )
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec_()

    def _on_settings_saved(self, settings: AppSettings) -> None:
        self.settings = settings
        self.transcriber.unload_local()
        self._setup_global_shortcut()
        self._apply_settings_to_ui()
        self._emit_ready_status()

    def _maybe_prompt_model_download(self) -> None:
        if self.settings.engine != "local" or model_ready(self.settings):
            return
        reply = QMessageBox.question(
            self,
            "Modelo local",
            "O VoxTalk usa por padrão o Parakeet local (mesmo do Orca, ~670 MB).\n\n"
            "Baixar agora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._download_model_in_background()

    def _download_model_in_background(self) -> None:
        if self._preparing_model:
            return
        self._preparing_model = True
        self.bus.status.emit("A baixar modelo Parakeet (~670 MB)…")

        def work() -> None:
            try:
                ensure_parakeet(
                    self.settings,
                    progress=lambda p, msg: self.bus.status.emit(
                        f"Modelo: {msg} ({p * 100:.0f}%)"
                    ),
                )
                self.bus.status.emit(
                    f"Modelo local pronto. Atalho: {self._shortcut_label()}"
                )
            except Exception as exc:
                self.bus.error.emit(f"Falha ao baixar modelo: {exc}")
            finally:
                self._preparing_model = False

        threading.Thread(target=work, daemon=True).start()

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(_mic_icon(False), self)
        menu = QMenu()
        act_show = QAction("Mostrar", self)
        act_show.triggered.connect(self.showNormal)
        act_toggle = QAction("Gravar / Parar", self)
        act_toggle.triggered.connect(self.toggle_recording)
        act_settings = QAction("Configurações…", self)
        act_settings.triggered.connect(self.open_settings)
        act_quit = QAction("Sair", self)
        act_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(act_show)
        menu.addAction(act_toggle)
        menu.addAction(act_settings)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("VoxTalk")
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_recording(self) -> None:
        if self._busy or self._preparing_model:
            return
        if self.recorder.is_recording:
            self._stop_and_transcribe()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if self.settings.engine == "local" and not model_ready(self.settings):
            reply = QMessageBox.question(
                self,
                "Modelo local",
                "O modelo Parakeet ainda não está instalado (~670 MB).\n"
                "Baixar agora?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._download_model_in_background()
            else:
                self.open_settings()
            return
        if self.settings.engine == "openai" and not self.settings.openai_api_key.strip():
            QMessageBox.warning(
                self,
                "VoxTalk",
                "Configure a chave OpenAI em Configurações, ou mude para o motor local.",
            )
            self.open_settings()
            return

        try:
            self.recorder.start()
        except Exception as exc:
            self.bus.error.emit(f"Não foi possível abrir o microfone: {exc}")
            return

        self.record_btn.setText("■  Parar")
        self.record_btn.setProperty("recording", "true")
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.bus.status.emit("Gravando… fale agora. Pressione o atalho de novo para parar.")
        self.level_bar.setValue(0)
        self._bubble_hide_timer.stop()
        self.bubble.show_recording()
        self._level_timer.start()
        if hasattr(self, "tray"):
            self.tray.setIcon(_mic_icon(True))

    def _stop_and_transcribe(self) -> None:
        self._level_timer.stop()
        self.level_bar.setValue(0)
        audio = self.recorder.stop()

        self.record_btn.setText("●  Gravar")
        self.record_btn.setProperty("recording", "false")
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        if hasattr(self, "tray"):
            self.tray.setIcon(_mic_icon(False))

        duration = audio.size / MicrophoneRecorder.SAMPLE_RATE if audio.size else 0
        if duration < 0.4:
            self.bus.status.emit("Gravação muito curta — tente de novo.")
            self.bubble.show_empty("Gravação muito curta")
            self._bubble_hide_timer.start(2500)
            return

        self._persist_ui_prefs()
        self._busy = True
        engine = ENGINE_LABELS.get(self.settings.engine, self.settings.engine)
        self.bus.status.emit(f"Transcrevendo ({duration:.1f}s) via {engine}…")
        self.bubble.show_transcribing()
        threading.Thread(
            target=self._run_transcribe,
            args=(audio,),
            daemon=True,
        ).start()

    def _run_transcribe(self, audio) -> None:
        try:
            result = self.transcriber.transcribe(audio, self.settings)
            self.bus.transcript.emit(result.text, result.language)
        except Exception as exc:
            self.bus.error.emit(f"Erro na transcrição: {exc}")
        finally:
            self._busy = False

    def _on_transcript(self, text: str, language: str) -> None:
        if not text:
            self.bus.status.emit("Nenhuma fala detectada.")
            self.bubble.show_empty()
            self._bubble_hide_timer.start(3000)
            return
        current = self.text.toPlainText().strip()
        if current:
            self.text.append(text)
        else:
            self.text.setPlainText(text)

        lang_name = LANGUAGES.get(language, language)
        engine = ENGINE_LABELS.get(self.settings.engine, self.settings.engine)
        self.bubble.show_result(text)
        self.bus.status.emit(f"Pronto ({engine}). Idioma: {lang_name}")
        # Com a janela do VoxTalk em foco, colar cairia nela mesma
        if self.settings.insert_into_focused and not self.isActiveWindow():
            self._inject_async(text)
        elif self.auto_copy.isChecked():
            try:
                pyperclip.copy(text)
                self.bubble.copy_btn.setText("Copiado!")
                self.bubble.title.setText("Copiado ✓")
                self.bus.status.emit(
                    f"Pronto ({engine}, {lang_name}). Texto copiado."
                )
            except Exception:
                pass
        # Mantém o balão um tempo para colar / revisar
        self._bubble_hide_timer.start(12_000)

    def _inject_async(self, text: str) -> None:
        combo = self.settings.paste_combo
        restore = not self.auto_copy.isChecked()

        def work() -> None:
            try:
                self._injector.inject(text, combo=combo, restore_clipboard=restore)
                self.bus.injected.emit(True, "")
            except InjectionUnavailable as exc:
                self.bus.injected.emit(False, str(exc))
            except Exception as exc:
                self.bus.injected.emit(False, f"Falha ao inserir texto: {exc}")

        threading.Thread(target=work, daemon=True).start()

    def _on_injected(self, ok: bool, message: str) -> None:
        if ok:
            self.bubble.title.setText("Inserido ✓")
            self.bus.status.emit("Texto inserido no app em foco.")
            return
        self.bubble.title.setText("Copiado ✓")
        self.bus.status.emit(message)
        if not self._inject_warned:
            self._inject_warned = True
            if hasattr(self, "tray"):
                self.tray.showMessage("VoxTalk", message, QSystemTrayIcon.Warning, 6000)

    def _on_error(self, message: str) -> None:
        self._busy = False
        self.bus.status.emit(message)
        self.bubble.show_empty(message[:48])
        self._bubble_hide_timer.start(4000)
        QMessageBox.warning(self, "VoxTalk", message)

    def _poll_level(self) -> None:
        if self.recorder.is_recording:
            self.bus.recording_level.emit(self.recorder.level())

    def copy_text(self) -> None:
        text = self.text.toPlainText().strip()
        if text:
            pyperclip.copy(text)
            self.bus.status.emit("Texto copiado.")

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "tray") and self.tray.isVisible():
            self.hide()
            self.tray.showMessage(
                "VoxTalk",
                f"Continua em segundo plano. Atalho: {self._shortcut_label()}",
                QSystemTrayIcon.Information,
                2000,
            )
            event.ignore()
            return
        self._shutdown()
        event.accept()

    def _shutdown(self) -> None:
        self._level_timer.stop()
        self._bubble_hide_timer.stop()
        if hasattr(self, "bubble"):
            self.bubble.hide()
        if self.recorder.is_recording:
            self.recorder.stop()
        if self._hotkey is not None:
            self._hotkey.stop()
        self._injector.close()


def run() -> None:
    import sys

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("VoxTalk")

    # Paleta escura base
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0f1419"))
    palette.setColor(QPalette.WindowText, QColor("#e7ecf1"))
    app.setPalette(palette)

    # Instância única: uma segunda execução só traz a janela existente para frente
    socket_path = default_socket_path()
    window: Optional[MainWindow] = None
    server = InstanceServer(
        socket_path,
        lambda cmd: window.on_external_command(cmd) if window is not None else None,
    )
    if not server.start():
        send_command("show", socket_path)
        return

    window = MainWindow()
    window.show()
    code = app.exec_()
    server.stop()
    sys.exit(code)
