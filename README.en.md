# Baduk Studio

[한국어](README.md) | **English**

A Go (Baduk) desktop app that runs the KataGo neural network on a **real GPU**.
It aims for UI/features similar to the chess app
[wogur110/chess-game](https://github.com/wogur110/chess-game) (PySide6 + Stockfish),
but the moves are predicted by KataGo rather than a built-in engine.

- **Analysis:** KataGo **28-block (b28)** network — win rate, score lead, candidate moves, ownership
- **Opponent:** KataGo **human-net** (human imitation) — rank-based difficulty from 20k to 9d/pro
- **Language:** Korean / English — switch from the top of the sidebar (preference is saved)
- **Engine status:** the sidebar shows model **loading / ready** at startup (colored indicator)
- **Board aids:** hover **ghost stone** for the next move, hover a candidate to preview its **variation (next 10 moves)**, plus **move-order** and **territory** toggles
- **Score estimate:** one button runs a deep (high-visit) analysis and shows **each side's territory** on the board plus **who leads by how many points**
- **Lizzie-style UI:** a bottom **win-rate graph** (Black win rate over the whole game, click to jump) + **heatmap candidate moves** (blue=best→red, win% + visits) + a board-centric layout
- **Shortcuts & auto-analyze:** `Space` (toggle analysis) · `←/→` (navigate) · `Home/End` · `A` (**auto-analyze** — step through the whole game) · `P` (pass) · `Ctrl+Z` (undo)

**▶ [Download the latest Windows build](https://github.com/wogur110/go-game/releases/latest)** — extract the
zip and run `BadukStudio.exe`. On first launch the app downloads the KataGo engine (OpenCL by default) and
networks. ([All releases](https://github.com/wogur110/go-game/releases))

> Status: **M0–M4 complete.** Rank-based play vs the human-net + live analysis (win/score bar, candidate
> overlay, ownership heatmap) + two-pass KataGo scoring + SGF save/load + **PyInstaller packaging / GitHub
> Actions Windows release.** 11 bugs fixed via an adversarial multi-agent review. Verified on an RTX 5060 Ti
> (Blackwell) + WSL2.

## Decisions

| Item | Choice |
|---|---|
| Stack | Python + PySide6 (reuses the chess-game structure) |
| Default engine | KataGo 28-block `b28` (also: b18 / human-net) |
| GPU backend | NVIDIA CUDA/TensorRT (dev/run on WSL2 Linux) |
| Difficulty | human-net by rank (b28 stays full-strength for analysis) |
| v1 scope | Play tab — game + live analysis overlays + SGF; joseki/fuseki study is v2 |
| Distribution | Windows release + Linux dev; binary/weights downloaded on first run |
| Rules | 19×19 · Chinese · komi 7.5 · handicap · two passes → KataGo scoring |

## Install / first run (NVIDIA GPU)

No separate CUDA/cuDNN install is needed — the runtime comes from pip wheels and
[app/engine/env.py](app/engine/env.py) sets up `LD_LIBRARY_PATH` automatically (no manual export).

```bash
pip install -r requirements.txt   # PySide6 + sgfmill + CUDA12 runtime wheels (cudnn/cublas/cudart)
python download_katago.py         # KataGo build + networks (b28/b18/human-net)
python -m app.engine.smoke        # engine check (analysis + human-net genmove)
python main.py --smoke            # game check (human→AI round-trip, headless)
python main.py                    # launch the GUI (play vs the human-net)
```

> With conda: `conda create -n go-game python=3.11 -y && conda run -n go-game pip install -r requirements.txt`,
> then `conda run -n go-game python main.py`.

What `download_katago.py` fetches (both git-ignored):
- engine binary → `engines/<os>/` (auto-picks the OS/backend asset from GitHub release `v1.16.5`)
- networks → `models/`: `b28` (default analysis), `b18` (faster), `b18c384nbt-humanv0` (human-net play)

The default backend is OS-aware: **Linux → CUDA 12.8** (satisfied by the pip wheels), **Windows → OpenCL**
(the CUDA build needs ~1.3GB of CUDA/cuDNN DLLs the user lacks; OpenCL runs on just the GPU driver's
`OpenCL.dll`). Override with `--backend trt|opencl|eigen`. Blackwell (RTX 50-series) needs a CUDA 12.8+ build.

## Layout

```
download_katago.py        engine binary + network downloader (auto-selects asset via the GitHub API)
configs/
  analysis.cfg            KataGo analysis-engine config (win rate reported from Black's POV)
  gtp_human.cfg           KataGo GTP human-net config (humanSLProfile = rank)
app/
  i18n.py                 Korean/English strings + QSettings persistence + live language switch
  goban.py                Go rules: captures, ko, suicide, pass, two-pass game-over, area scoring
  board_widget.py         board rendering + click-to-place + candidate/ownership overlays
  game_controller.py      game state, Human/AI, generation counter, undo/review, SGF, scoring
  sidebar.py / theme.py   win bar, candidate panel, move list, controls / dark theme
  sgf_io.py               SGF save/load (sgfmill)
  engine/
    coords.py             internal (x,y) ↔ GTP coords (A19, Q16 …)
    networks.py           selectable network registry (b28 default)
    discovery.py          find katago / networks / configs (PyInstaller + PATH aware)
    analysis_client.py    `katago analysis` JSON client (analysis role)
    gtp_client.py         `katago gtp` human-net client (play role)
    engine_manager.py     Qt wrapper over both engines (signals, worker thread)
```

## Engine integration

Follows the chess app's **two-engine (play/analysis)** split:

- **Analysis** = `katago analysis -config configs/analysis.cfg -model models/<b28>` — one JSON query per
  position, returning `moveInfos` (win rate, `scoreLead`, visits, pv) and `ownership`. Results come back via
  callbacks, marshalled to the GUI thread by Qt signals.
- **Play** = `katago gtp -model <b28> -human-model b18c384nbt-humanv0 -config gtp_human.cfg
  -override-config humanSLProfile=rank_5k` — `genmove` produces human-like moves for the chosen rank; the
  process restarts when the rank changes.

## Roadmap

- **M0 — engine spike ✅**: downloader, analysis/human-net clients, headless check
- **M1 — rules + board + play ✅**: rules engine, board widget (render + click-to-place), `GameController`,
  Qt `EngineManager`, real human↔human-net games
- **M2 — analysis UI ✅**: win/score bar, candidate overlay, ownership heatmap, net selector (b28/b18), sidebar
- **M3 — endgame ✅**: two-pass KataGo `scoreLead` scoring (dead stones reflected in ownership), SGF
- **M4 — packaging ✅**: PyInstaller `baduk_studio.spec` (engine excluded, downloaded on first run),
  `build_linux.sh`/`build_windows.bat`, GitHub Actions (Ubuntu test + build-smoke → Windows build/release)
- **In-app engine download ✅**: first-run dialog with backend picker + progress
- **v2**: joseki / fuseki study tab

## Build / distribute

```bash
./build_linux.sh            # dist/BadukStudio/BadukStudio (dev)
# Windows: build_windows.bat → dist\BadukStudio\BadukStudio.exe
```

The engine (KataGo binary + networks) isn't bundled (size + GPU deps) — the app **downloads it**:

```bash
BadukStudio --download                 # default backend: Windows=OpenCL, Linux=CUDA 12.8 (override with --backend)
```

[.github/workflows/build.yml](.github/workflows/build.yml): on push to main / PR / tag, Ubuntu runs the
rules+SGF tests and the engine-free `--build-smoke`; windows-latest builds the exe, smoke-tests it, and zips
it; a `v*` tag attaches the zip to a GitHub Release. (PyInstaller can't cross-compile — the Windows exe is
built on Windows.)
