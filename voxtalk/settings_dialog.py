"""Diálogo de configuração: motor local/nuvem, modelo e chave OpenAI."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
)

from . import gnome_shortcut
from .model_catalog import PARAKEET_DESCRIPTION, PARAKEET_LABEL, PARAKEET_TOTAL_BYTES
from .model_manager import ensure_parakeet, model_ready, model_status_label
from .settings import AppSettings, OpenAiModel, save_settings
from .transcriber import ENGINE_LABELS


class _DownloadBus(QObject):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(bool, str)  # ok, message


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal(object)  # AppSettings

    def __init__(
        self,
        settings: AppSettings,
        parent=None,
        *,
        on_unload_local: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configurações — VoxTalk")
        self.setMinimumWidth(480)
        self._settings = settings
        self._on_unload_local = on_unload_local
        self._cancel_download = False
        self._downloading = False
        self._bus = _DownloadBus(self)
        self._bus.progress.connect(self._on_download_progress)
        self._bus.finished.connect(self._on_download_finished)
        self._build()
        self._sync_engine_ui()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        intro = QLabel(
            "Padrão: reconhecimento <b>local</b> (Parakeet, mesmo motor do Orca). "
            "Opcional: nuvem OpenAI quando quiser."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)

        self.engine_combo = QComboBox()
        for key, label in ENGINE_LABELS.items():
            self.engine_combo.addItem(label, key)
        idx = self.engine_combo.findData(self._settings.engine)
        self.engine_combo.setCurrentIndex(max(0, idx))
        self.engine_combo.currentIndexChanged.connect(self._sync_engine_ui)
        form.addRow("Motor:", self.engine_combo)

        self.openai_model = QComboBox()
        self.openai_model.addItem("GPT-4o mini Transcribe (barato)", "gpt-4o-mini-transcribe")
        self.openai_model.addItem("GPT-4o Transcribe (mais preciso)", "gpt-4o-transcribe")
        midx = self.openai_model.findData(self._settings.openai_model)
        self.openai_model.setCurrentIndex(max(0, midx))
        form.addRow("Modelo nuvem:", self.openai_model)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setText(self._settings.openai_api_key)
        self.api_key.setPlaceholderText("sk-…")
        form.addRow("Chave OpenAI:", self.api_key)

        self.insert_check = QCheckBox("Inserir o texto no app em foco")
        self.insert_check.setChecked(self._settings.insert_into_focused)
        form.addRow("Saída:", self.insert_check)

        self.paste_combo = QComboBox()
        self.paste_combo.addItem("Ctrl+V", "ctrl+v")
        self.paste_combo.addItem("Ctrl+Shift+V (terminais)", "ctrl+shift+v")
        pidx = self.paste_combo.findData(self._settings.paste_combo)
        self.paste_combo.setCurrentIndex(max(0, pidx))
        self.insert_check.toggled.connect(self.paste_combo.setEnabled)
        self.paste_combo.setEnabled(self._settings.insert_into_focused)
        form.addRow("Colar com:", self.paste_combo)

        on_gnome = gnome_shortcut.is_gnome()
        self.gnome_check = QCheckBox("Registrar atalho global no GNOME")
        self.gnome_check.setChecked(self._settings.gnome_shortcut)
        self.gnome_check.setEnabled(on_gnome)
        form.addRow("Atalho:", self.gnome_check)

        self.shortcut_edit = QLineEdit(self._settings.shortcut)
        self.shortcut_edit.setPlaceholderText("F9, <Super>h, <Ctrl><Alt>space…")
        self.shortcut_edit.setEnabled(on_gnome and self._settings.gnome_shortcut)
        self.gnome_check.toggled.connect(self.shortcut_edit.setEnabled)
        form.addRow("Tecla (GNOME):", self.shortcut_edit)

        layout.addLayout(form)

        local_box = QVBoxLayout()
        self.local_title = QLabel(f"<b>{PARAKEET_LABEL}</b>")
        local_box.addWidget(self.local_title)
        self.local_desc = QLabel(PARAKEET_DESCRIPTION)
        self.local_desc.setWordWrap(True)
        self.local_desc.setObjectName("muted")
        local_box.addWidget(self.local_desc)

        self.model_status = QLabel(model_status_label(self._settings))
        local_box.addWidget(self.model_status)

        row = QHBoxLayout()
        self.download_btn = QPushButton("Baixar modelo local (~670 MB)")
        self.download_btn.clicked.connect(self._start_download)
        row.addWidget(self.download_btn)
        self.cancel_dl_btn = QPushButton("Cancelar")
        self.cancel_dl_btn.setEnabled(False)
        self.cancel_dl_btn.clicked.connect(self._cancel_dl)
        row.addWidget(self.cancel_dl_btn)
        local_box.addLayout(row)

        self.dl_progress = QProgressBar()
        self.dl_progress.setRange(0, 1000)
        self.dl_progress.setValue(0)
        self.dl_progress.setTextVisible(True)
        local_box.addWidget(self.dl_progress)

        self.dl_status = QLabel("")
        self.dl_status.setWordWrap(True)
        local_box.addWidget(self.dl_status)

        layout.addLayout(local_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(
            """
            QLabel#muted { color: #94a3b8; font-size: 12px; }
            QLineEdit, QComboBox {
                background: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 6px 10px;
                color: #f8fafc;
            }
            """
        )

        if model_ready(self._settings):
            self.download_btn.setText("Modelo já instalado (verificar / rebaixar)")

    def _sync_engine_ui(self) -> None:
        cloud = self.engine_combo.currentData() == "openai"
        self.openai_model.setEnabled(cloud)
        self.api_key.setEnabled(cloud)

    def _collect(self) -> AppSettings:
        engine = self.engine_combo.currentData()
        model: OpenAiModel = self.openai_model.currentData()
        return AppSettings(
            engine=engine,
            openai_model=model,
            openai_api_key=self.api_key.text().strip(),
            language=self._settings.language,
            auto_copy=self._settings.auto_copy,
            models_dir=self._settings.models_dir,
            insert_into_focused=self.insert_check.isChecked(),
            paste_combo=self.paste_combo.currentData(),
            shortcut=self.shortcut_edit.text().strip() or "F9",
            gnome_shortcut=self.gnome_check.isChecked(),
        )

    def _save(self) -> None:
        settings = self._collect()
        if settings.engine == "openai" and not settings.openai_api_key:
            QMessageBox.warning(
                self,
                "VoxTalk",
                "Para usar a nuvem, cole uma chave da API OpenAI "
                "(ou escolha o motor local).",
            )
            return
        if settings.engine == "local" and not model_ready(settings):
            QMessageBox.information(
                self,
                "VoxTalk",
                "O motor local precisa do modelo Parakeet (~670 MB).\n"
                "Clique em «Baixar modelo local» antes de gravar, "
                "ou o VoxTalk pedirá o download na primeira uso.",
            )
        save_settings(settings)
        self.settings_saved.emit(settings)
        self.accept()

    def _cancel_dl(self) -> None:
        self._cancel_download = True

    def _start_download(self) -> None:
        if self._downloading:
            return
        self._cancel_download = False
        self._downloading = True
        self.download_btn.setEnabled(False)
        self.cancel_dl_btn.setEnabled(True)
        self.dl_status.setText("A iniciar download…")
        settings = self._collect()

        def work() -> None:
            try:
                ensure_parakeet(
                    settings,
                    progress=lambda p, msg: self._bus.progress.emit(p, msg),
                    cancel_check=lambda: self._cancel_download,
                )
                if self._on_unload_local:
                    self._on_unload_local()
                self._bus.finished.emit(True, "Modelo local pronto.")
            except Exception as exc:
                self._bus.finished.emit(False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_download_progress(self, fraction: float, message: str) -> None:
        self.dl_progress.setValue(int(fraction * 1000))
        mb = PARAKEET_TOTAL_BYTES / (1024 * 1024)
        self.dl_progress.setFormat(f"{fraction * 100:.0f}% de ~{mb:.0f} MB")
        self.dl_status.setText(message)

    def _on_download_finished(self, ok: bool, message: str) -> None:
        self._downloading = False
        self.download_btn.setEnabled(True)
        self.cancel_dl_btn.setEnabled(False)
        self.model_status.setText(model_status_label(self._collect()))
        self.dl_status.setText(message)
        if ok:
            self.dl_progress.setValue(1000)
            self.download_btn.setText("Modelo já instalado (verificar / rebaixar)")
        else:
            QMessageBox.warning(self, "Download", message)
