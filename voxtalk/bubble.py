"""Balão flutuante transparente — canto superior direito."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QPoint
from PyQt5.QtGui import QFont, QGuiApplication
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QProgressBar,
)

from .hotkey import hotkey_label


class RecordingBubble(QWidget):
    """Overlay sempre no topo: gravação → texto pronto para copiar."""

    copy_requested = pyqtSignal(str)
    stop_requested = pyqtSignal()
    dismissed = pyqtSignal()

    MARGIN = 16
    WIDTH = 340

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            # Não roubar o foco: o texto é colado no app que estava em uso
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(self.WIDTH)

        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

        self._build()
        self.hide()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("bubble")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        header = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setObjectName("recDot")
        self.title = QLabel("Gravando…")
        self.title.setObjectName("bubbleTitle")
        header.addWidget(self.dot)
        header.addWidget(self.title, stretch=1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("bubbleClose")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self._dismiss)
        header.addWidget(self.close_btn)
        card_layout.addLayout(header)

        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        self.level.setTextVisible(False)
        self.level.setFixedHeight(4)
        self.level.setObjectName("bubbleLevel")
        card_layout.addWidget(self.level)

        self.hint = QLabel(f"{hotkey_label()} para parar")
        self.hint.setObjectName("bubbleHint")
        self.hint.setWordWrap(True)
        card_layout.addWidget(self.hint)

        self.text = QTextEdit()
        self.text.setObjectName("bubbleText")
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(72)
        self.text.setMaximumHeight(160)
        self.text.setPlaceholderText("O texto aparece aqui…")
        self.text.setFont(QFont("Ubuntu", 11))
        self.text.hide()
        card_layout.addWidget(self.text)

        actions = QHBoxLayout()
        self.stop_btn = QPushButton("Parar")
        self.stop_btn.setObjectName("bubbleStop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        actions.addWidget(self.stop_btn)

        self.copy_btn = QPushButton("Copiar")
        self.copy_btn.setObjectName("bubbleCopy")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy)
        self.copy_btn.hide()
        actions.addWidget(self.copy_btn)
        card_layout.addLayout(actions)

        outer.addWidget(self.card)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#bubble {
                background-color: rgba(12, 18, 28, 200);
                border: 1px solid rgba(94, 234, 212, 140);
                border-radius: 16px;
            }
            QLabel#recDot {
                color: #ef4444;
                font-size: 14px;
                padding-right: 4px;
            }
            QLabel#bubbleTitle {
                color: #f1f5f9;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#bubbleHint {
                color: #94a3b8;
                font-size: 11px;
            }
            QTextEdit#bubbleText {
                background: rgba(26, 35, 50, 180);
                border: 1px solid rgba(71, 85, 105, 160);
                border-radius: 8px;
                padding: 8px;
                color: #f8fafc;
                selection-background-color: #0d9488;
            }
            QProgressBar#bubbleLevel {
                background: rgba(30, 41, 59, 180);
                border: none;
                border-radius: 2px;
            }
            QProgressBar#bubbleLevel::chunk {
                background: #ef4444;
                border-radius: 2px;
            }
            QPushButton#bubbleClose {
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 12px;
                border-radius: 12px;
            }
            QPushButton#bubbleClose:hover { color: #f1f5f9; background: rgba(255,255,255,30); }
            QPushButton#bubbleStop, QPushButton#bubbleCopy {
                background: rgba(15, 118, 110, 200);
                border: 1px solid #14b8a6;
                border-radius: 8px;
                padding: 6px 12px;
                color: #f0fdfa;
                font-weight: 600;
            }
            QPushButton#bubbleStop:hover, QPushButton#bubbleCopy:hover {
                background: rgba(20, 184, 166, 220);
            }
            QPushButton#bubbleStop {
                background: rgba(185, 28, 28, 200);
                border-color: #ef4444;
            }
            QPushButton#bubbleStop:hover { background: rgba(220, 38, 38, 220); }
            """
        )

    def _place_top_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        x = geo.right() - self.width() - self.MARGIN
        y = geo.top() + self.MARGIN
        self.move(QPoint(x, y))

    def show_recording(self) -> None:
        self.dot.setText("●")
        self.dot.setStyleSheet("color: #ef4444; font-size: 14px;")
        self.title.setText("Gravando…")
        self.hint.setText(f"Fale agora · {hotkey_label()} para parar")
        self.hint.show()
        self.level.show()
        self.level.setValue(0)
        self.text.clear()
        self.text.hide()
        self.stop_btn.show()
        self.copy_btn.hide()
        self._place_top_right()
        self._fade_in()

    def show_result(self, text: str) -> None:
        self.dot.setText("✓")
        self.dot.setStyleSheet("color: #5eead4; font-size: 14px;")
        self.title.setText("Pronto para copiar")
        self.hint.hide()
        self.level.hide()
        self.text.setPlainText(text)
        self.text.show()
        self.text.selectAll()
        self.stop_btn.hide()
        self.copy_btn.setText("Copiar")
        self.copy_btn.show()
        self._place_top_right()
        if self.isVisible():
            self.raise_()
        else:
            self._fade_in()

    def show_empty(self, message: str = "Nenhuma fala detectada") -> None:
        self.dot.setText("!")
        self.dot.setStyleSheet("color: #fbbf24; font-size: 14px;")
        self.title.setText(message)
        self.hint.setText("Tente gravar de novo")
        self.hint.show()
        self.level.hide()
        self.text.hide()
        self.stop_btn.hide()
        self.copy_btn.hide()
        self._place_top_right()
        if self.isVisible():
            self.raise_()
        else:
            self._fade_in()

    def show_transcribing(self) -> None:
        self.dot.setText("…")
        self.dot.setStyleSheet("color: #5eead4; font-size: 14px;")
        self.title.setText("Transcrevendo…")
        self.hint.setText("Quase lá")
        self.hint.show()
        self.level.hide()
        self.stop_btn.hide()
        self.copy_btn.hide()
        self._place_top_right()
        if self.isVisible():
            self.raise_()
        else:
            self._fade_in()

    def set_level(self, value: float) -> None:
        self.level.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _copy(self) -> None:
        text = self.text.toPlainText().strip()
        if text:
            self.copy_requested.emit(text)
            self.copy_btn.setText("Copiado!")
            self.title.setText("Copiado ✓")

    def _dismiss(self) -> None:
        self._fade_out()
        self.dismissed.emit()

    def fade_out(self) -> None:
        self._fade_out()

    def _fade_in(self) -> None:
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._fade.stop()
        try:
            self._fade.finished.disconnect()
        except TypeError:
            pass
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _fade_out(self) -> None:
        if not self.isVisible():
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        try:
            self._fade.finished.disconnect()
        except TypeError:
            pass
        self._fade.finished.connect(self.hide)
        self._fade.start()
