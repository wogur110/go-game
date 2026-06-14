"""First-run dialog that fetches the KataGo engine + networks (in-app).

Shown when the engine is missing. Runs download_katago.download_all() on a worker
thread and streams progress; on success the caller rescans + starts the engine.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

import download_katago
from . import theme
from .engine.networks import NETWORKS
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

    def __init__(self, task, cancel: Optional[threading.Event] = None) -> None:
        super().__init__()
        self._task = task          # callable(on_progress, should_cancel) that downloads
        self._cancel = cancel

    def run(self) -> None:
        should_cancel = self._cancel.is_set if self._cancel is not None else (lambda: False)
        try:
            self._task(lambda msg, frac: self.progressed.emit(msg, frac), should_cancel)
            self.finished.emit(True, "")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))


class _CancellableMixin:
    """Crash-safe dismissal for a dialog driving a download :class:`_Worker` thread.

    A QThread destroyed while still running aborts the process, so we never tear
    one down on Escape / the window-close (X) button. Instead dismissal sets a
    cooperative cancel flag (``self._cancel``, polled by the download loop) and the
    dialog closes only once the worker's ``finished`` signal arrives — see each
    dialog's ``_on_finished``, which calls ``self.reject()`` after quitting the
    thread, by which point ``_running()`` is False and dismissal goes through.
    """

    def _running(self) -> bool:
        thread = getattr(self, "_thread", None)
        return thread is not None and thread.isRunning()

    def _request_cancel(self) -> None:
        self._cancel.set()
        self.status.setText(t("dl.cancelling"))

    def reject(self) -> None:  # Escape key + Cancel button
        if self._running():
            self._request_cancel()
            return
        super().reject()

    def closeEvent(self, event) -> None:  # window-manager X
        if self._running():
            self._request_cancel()
            event.ignore()
            return
        super().closeEvent(event)


class DownloadDialog(_CancellableMixin, QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("dl.title"))
        self.setMinimumWidth(460)
        self.downloaded = False
        self._cancel = threading.Event()
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
        self._worker = _Worker(
            lambda op, cancel: download_katago.download_all(
                backend, on_progress=op, should_cancel=cancel),
            self._cancel)
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
        elif self._cancel.is_set():
            self.reject()                    # cancelled — thread stopped, now safe to close
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


class _ProgressDialog(_CancellableMixin, QDialog):
    """Runs a single download task on a worker thread; auto-starts when shown.

    The button doubles as a live Cancel while downloading (the b40 net is 823MB):
    pressing it — or Escape / the window X — flags the download to stop rather than
    killing the thread (see :class:`_CancellableMixin`)."""

    def __init__(self, parent, title, task) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.ok = False
        self._task = task
        self._cancel = threading.Event()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        lay = QVBoxLayout(self)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        lay.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {theme.TEXT_DIM};")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        self.close_btn = QPushButton(t("dl.cancel"))
        self.close_btn.clicked.connect(self.reject)
        row.addWidget(self.close_btn)
        lay.addLayout(row)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._thread is None:
            self._thread = QThread(self)
            self._worker = _Worker(self._task, self._cancel)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.progressed.connect(self._on_progress)
            self._worker.finished.connect(self._on_finished)
            self._thread.start()

    def _on_progress(self, message: str, fraction: float) -> None:
        self.status.setText(message)
        if fraction < 0:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(fraction * 100))

    def _on_finished(self, ok: bool, message: str) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self.ok = ok
        if ok:
            self.accept()
        elif self._cancel.is_set():
            self.reject()                    # cancelled — thread stopped, now safe to close
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
            self.status.setText(t("dl.failed", msg=message))
            self.close_btn.setText(t("dl.later"))


def download_network(parent, key: str) -> bool:
    """Modally download a single network (used when a not-yet-downloaded model is
    selected). Returns True if it completed."""
    if NETWORKS.get(key) is None:
        return False
    dlg = _ProgressDialog(parent, t("net.download_title"),
                          lambda op, cancel: download_katago.download_networks(
                              only=key, on_progress=op, should_cancel=cancel))
    dlg.status.setText(t("net.downloading", name=t("net." + key)))
    return dlg.exec() == QDialog.Accepted and dlg.ok
