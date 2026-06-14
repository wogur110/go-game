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
from .i18n import t


def _backend_choices():
    """OS-aware picker (first = recommended/default). On Windows the CUDA build
    needs ~1.3GB of CUDA/cuDNN DLLs the user lacks, so OpenCL (driver-provided)
    is the safe default; on Linux CUDA works via the bundled pip wheels."""
    if os.name == "nt":
        return [
            (t("dl.opencl_win"), "opencl"),
            (t("dl.cuda_win"), "cuda12.8"),
            (t("dl.eigen"), "eigen"),
        ]
    return [
        (t("dl.cuda_lin"), "cuda12.8"),
        (t("dl.trt"), "trt"),
        (t("dl.opencl"), "opencl"),
        (t("dl.eigen"), "eigen"),
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
        self.setWindowTitle(t("dl.title"))
        self.setMinimumWidth(460)
        self.downloaded = False
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        intro = QLabel(t("dl.intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel(t("dl.backend")))
        self.combo = QComboBox()
        for label, key in _backend_choices():
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
        self.later_btn = QPushButton(t("dl.later"))
        self.later_btn.clicked.connect(self.reject)
        self.dl_btn = QPushButton(t("dl.download"))
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
            self.status.setText(t("dl.failed", msg=message))
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
