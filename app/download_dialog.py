"""First-run dialog that fetches the KataGo engine + networks (in-app).

Shown when the engine is missing. Runs download_katago.download_all() on a worker
thread and streams progress; on success the caller rescans + starts the engine.
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

import download_katago
from . import theme

# Friendly backend choices for the picker (value = download_katago backend key).
_BACKENDS = [
    ("NVIDIA GPU · CUDA 12.8 (권장)", "cuda12.8"),
    ("NVIDIA GPU · TensorRT", "trt"),
    ("기타 GPU · OpenCL", "opencl"),
    ("CPU만 · Eigen (느림)", "eigen"),
]


class _Worker(QObject):
    progressed = Signal(str, float)
    finished = Signal(bool, str)

    def __init__(self, backend: str) -> None:
        super().__init__()
        self.backend = backend

    def run(self) -> None:
        try:
            download_katago.download_all(
                self.backend,
                on_progress=lambda msg, frac: self.progressed.emit(msg, frac))
            self.finished.emit(True, "완료")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))


class DownloadDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("KataGo 엔진 다운로드")
        self.setMinimumWidth(460)
        self.downloaded = False
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        intro = QLabel(
            "대국·분석에는 KataGo 엔진과 신경망(b28·휴먼넷)이 필요합니다 (약 400MB).\n"
            "GPU 백엔드를 고르고 다운로드하세요. 앱 옆에 저장되며 다음 실행부터는 자동 인식됩니다.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel("백엔드"))
        self.combo = QComboBox()
        for label, key in _BACKENDS:
            self.combo.addItem(label, key)
        row.addWidget(self.combo, 1)
        lay.addLayout(row)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        lay.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {theme.TEXT_DIM};")
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.later_btn = QPushButton("나중에")
        self.later_btn.clicked.connect(self.reject)
        self.dl_btn = QPushButton("다운로드")
        self.dl_btn.clicked.connect(self._start)
        btns.addWidget(self.later_btn)
        btns.addWidget(self.dl_btn)
        lay.addLayout(btns)

    def _start(self) -> None:
        self.dl_btn.setEnabled(False)
        self.combo.setEnabled(False)
        self.later_btn.setEnabled(False)
        backend = self.combo.currentData()
        self._thread = QThread(self)
        self._worker = _Worker(backend)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, message: str, fraction: float) -> None:
        self.status.setText(message)
        if fraction < 0:
            self.bar.setRange(0, 0)          # busy/indeterminate
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(fraction * 100))

    def _on_finished(self, ok: bool, message: str) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        if ok:
            self.downloaded = True
            self.accept()
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
            self.status.setText(f"실패: {message}")
            self.dl_btn.setEnabled(True)
            self.combo.setEnabled(True)
            self.later_btn.setEnabled(True)


def prompt_if_missing(parent, engine) -> bool:
    """If the engine is missing, offer the download dialog. Returns True if a
    download completed (caller should rescan + start)."""
    if engine.available:
        return False
    dlg = DownloadDialog(parent)
    dlg.exec()
    if dlg.downloaded:
        engine.rescan()
        return True
    return False
