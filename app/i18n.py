"""Lightweight i18n: Korean (default) + English, persisted via QSettings.

Usage:
    from .i18n import t, I18N
    label.setText(t("btn.new"))
    t("status.reviewing", view=3, total=10)
    I18N.languageChanged.connect(self.retranslate)   # live switch

Templates use str.format; pass the keys a template references as kwargs. Korean
and English templates may reference different keys (e.g. Korean adds "집"), so
pass every relevant value.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

LANGS = ["ko", "en"]
DEFAULT_LANG = "ko"
LANG_NAMES = [("ko", "한국어"), ("en", "English")]

STRINGS: dict[str, dict[str, str]] = {
    # -- app / window --
    "app.title": {"ko": "바둑 스튜디오", "en": "Baduk Studio"},

    # -- colors / players --
    "color.black": {"ko": "흑", "en": "Black"},
    "color.white": {"ko": "백", "en": "White"},
    "player.human": {"ko": "사람", "en": "Human"},
    "player.ai": {"ko": "AI", "en": "AI"},

    # -- sidebar controls --
    "ui.black_player": {"ko": "● 흑", "en": "● Black"},
    "ui.white_player": {"ko": "○ 백", "en": "○ White"},
    "ui.rank": {"ko": "급수", "en": "Rank"},
    "ui.net": {"ko": "분석망", "en": "Net"},
    "ui.candidates": {"ko": "후보수 (승률 · 집 · 방문)",
                      "en": "Candidates (win% · score · visits)"},
    "ui.language": {"ko": "언어", "en": "Language"},
    "btn.new": {"ko": "새 대국", "en": "New game"},
    "btn.pass": {"ko": "패스", "en": "Pass"},
    "btn.resign": {"ko": "기권", "en": "Resign"},
    "btn.undo": {"ko": "무르기", "en": "Undo"},
    "btn.sgf_save": {"ko": "SGF 저장", "en": "Save SGF"},
    "btn.sgf_load": {"ko": "SGF 불러오기", "en": "Load SGF"},
    "dlg.save_sgf": {"ko": "SGF 저장", "en": "Save SGF"},
    "dlg.load_sgf": {"ko": "SGF 불러오기", "en": "Open SGF"},
    "msg.saved": {"ko": "저장됨: {path}", "en": "Saved: {path}"},
    "msg.loaded": {"ko": "불러옴: {path}", "en": "Loaded: {path}"},

    # -- win bar --
    "winbar.waiting": {"ko": "분석 대기…", "en": "Waiting for analysis…"},
    "winbar.black_pct": {"ko": "{black} {pct:.0f}%", "en": "{black} {pct:.0f}%"},
    "winbar.white_pct": {"ko": "{pct:.0f}% {white}", "en": "{pct:.0f}% {white}"},
    "winbar.score": {"ko": "{side} {score:.1f}집", "en": "{side} +{score:.1f}"},

    # -- status line --
    "status.loading": {"ko": "엔진 로딩 중…", "en": "Loading engine…"},
    "status.reviewing": {"ko": "검토 중 — {view} / {total} 수",
                         "en": "Reviewing — move {view} / {total}"},
    "status.game_over": {"ko": "대국 종료 — {result}", "en": "Game over — {result}"},
    "status.turn": {"ko": "{turn} 차례 ({who}){extra}{passes}{wr}",
                    "en": "{turn} to move ({who}){extra}{passes}{wr}"},
    "status.thinking": {"ko": " · 생각 중…", "en": " · thinking…"},
    "status.last_pass": {"ko": " · 직전 패스", "en": " · opponent passed"},
    "status.winrate": {"ko": " · {black} 승률 {pct:.1f}%", "en": " · {black} {pct:.1f}%"},
    "status.empty_move": {"ko": "대국 엔진이 빈 수를 반환했습니다 — 다시 시도하세요",
                          "en": "The engine returned an empty move — please retry"},
    "status.unsupported_size": {
        "ko": "{size}×{size} 기보는 현재 미지원 (이 앱은 {n}로 전용)",
        "en": "{size}×{size} games aren't supported yet (this app is {n}×{n} only)"},

    # -- results --
    "result.resign": {"ko": "{winner} 불계승 (상대 기권)",
                      "en": "{winner} wins by resignation"},
    "result.win_by": {"ko": "{winner} {score:.1f}집승 ({src})",
                      "en": "{winner} +{score:.1f} ({src})"},
    "result.jigo": {"ko": "무승부/빅 ({src})", "en": "Draw / seki ({src})"},
    "result.counting": {"ko": "집계산 중…", "en": "Counting…"},
    "src.katago": {"ko": "KataGo", "en": "KataGo"},
    "src.count": {"ko": "집계산", "en": "area count"},

    # -- engine errors --
    "err.missing": {
        "ko": "엔진/네트워크/설정을 찾을 수 없습니다: {items} — 먼저 엔진을 다운로드하세요.",
        "en": "Engine/networks/configs not found: {items} — download the engine first."},
    "err.start_failed": {"ko": "엔진 시작 실패: {exc}", "en": "Engine failed to start: {exc}"},
    "err.play": {"ko": "대국 엔진 오류: {exc}", "en": "Play engine error: {exc}"},
    "err.net_missing": {"ko": "{label} 가중치가 없습니다 — download_katago --network {key}",
                        "en": "{label} weights missing — download_katago --network {key}"},

    # -- download dialog --
    "dl.title": {"ko": "KataGo 엔진 다운로드", "en": "Download KataGo engine"},
    "dl.intro": {
        "ko": "대국·분석에는 KataGo 엔진과 신경망(b28·휴먼넷)이 필요합니다 (약 400MB).\n"
              "GPU 백엔드를 고르고 다운로드하세요. 앱 옆에 저장되며 다음 실행부터는 자동 인식됩니다.",
        "en": "Playing/analysis needs the KataGo engine + networks (b28 · human-net, ~400MB).\n"
              "Pick a GPU backend and download. They're stored next to the app and auto-detected next time."},
    "dl.backend": {"ko": "백엔드", "en": "Backend"},
    "dl.later": {"ko": "나중에", "en": "Later"},
    "dl.download": {"ko": "다운로드", "en": "Download"},
    "dl.failed": {"ko": "실패: {msg}", "en": "Failed: {msg}"},
    "dl.opencl_win": {"ko": "GPU · OpenCL (권장, 드라이버만 필요)",
                      "en": "GPU · OpenCL (recommended, driver only)"},
    "dl.cuda_win": {"ko": "NVIDIA · CUDA 12.8 (CUDA+cuDNN 런타임 별도 설치 필요)",
                    "en": "NVIDIA · CUDA 12.8 (needs the CUDA+cuDNN runtime installed)"},
    "dl.cuda_lin": {"ko": "NVIDIA GPU · CUDA 12.8 (권장)", "en": "NVIDIA GPU · CUDA 12.8 (recommended)"},
    "dl.trt": {"ko": "NVIDIA GPU · TensorRT", "en": "NVIDIA GPU · TensorRT"},
    "dl.opencl": {"ko": "기타 GPU · OpenCL", "en": "Other GPU · OpenCL"},
    "dl.eigen": {"ko": "CPU만 · Eigen (느림)", "en": "CPU only · Eigen (slow)"},
}


class _I18N(QObject):
    languageChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings("BadukStudio", "BadukStudio")
        lang = self._settings.value("language", DEFAULT_LANG)
        self._lang = lang if lang in LANGS else DEFAULT_LANG

    @property
    def lang(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        if lang in LANGS and lang != self._lang:
            self._lang = lang
            self._settings.setValue("language", lang)
            self.languageChanged.emit(lang)

    def t(self, key: str, **kwargs) -> str:
        entry = STRINGS.get(key)
        if entry is None:
            return key
        s = entry.get(self._lang) or entry.get(DEFAULT_LANG) or key
        try:
            return s.format(**kwargs) if kwargs else s
        except (KeyError, IndexError, ValueError):
            return s


I18N = _I18N()


def t(key: str, **kwargs) -> str:
    return I18N.t(key, **kwargs)
