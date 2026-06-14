# Baduk Studio (바둑 스튜디오)

**한국어** | [English](README.en.md)

KataGo 신경망을 **실제 GPU**로 구동하는 바둑 데스크톱 프로그램. 체스 프로그램
[wogur110/chess-game](https://github.com/wogur110/chess-game)(PySide6 + Stockfish)와
비슷한 UI/기능을 목표로 하되, 다음 수는 내장 알고리즘이 아니라 KataGo가 예측합니다.

- **분석:** KataGo **28블록(b28)** 네트워크 — 승률·집수·후보수·영역(ownership)
- **분석 엔진 선택:** 사이드바에서 **40블록(최강·느림) / 28블록(권장) / 18블록(빠름)** 전환 — 더 강한 40블록(zhizi, ~430 Elo↑)을 고르면 미보유 시 진행률 다이얼로그로 **자동 다운로드** 후 적용. 엔진을 다시 로드하는 동안 상태 표시등은 **주황(로딩)**으로 유지되고, 새 신경망이 GPU에 완전히 올라오면 **초록(준비 완료)**으로 바뀜
- **대국 상대:** KataGo **휴먼넷**(사람 모방) — 20급~9단/프로 급수별 난이도
- **언어:** 한국어 / English — 사이드바 상단에서 전환(설정 저장)
- **엔진 상태 표시:** 시작 시 모델 **로딩 중 / 준비 완료**를 사이드바에 색상 점으로 표시
- **보드 보조:** **우클릭으로 무르기**(착수 취소), 호버 시 다음 착수 **미리보기(반투명 돌)**, 추천수(리스트·**바둑판 위 후보수** 모두) 호버 시 **향후 변화도(다음 10수)** 표시, **착점 순서**·**형세 판단** 토글
- **정밀 형세 판단:** 버튼 한 번으로 깊은 분석(고visit)을 돌려 **서로의 집**을 보드에 표시하고 **몇 집 우세**인지 알려줌
- **Lizzie 스타일 UI:** 하단 **승률 그래프**(대국 전체 흑 승률, 클릭해 수 이동) + **히트맵 후보수**(파랑=최선→빨강, 승률%+방문수) + 보드 중심 레이아웃
- **단축키 & 자동 분석:** `Space`(분석 켜기/끄기) · `←/→`(이동) · `Home/End` · `A`(**자동 진행** — 대국 전체를 한 수씩 자동 분석) · `P`(패스) · `Ctrl+Z`(무르기)
- **연속 분석 (Lizzie 방식):** ~0.5초 내 추천수 표시 후 **계속 탐색하며 visits·승률을 실시간 갱신**(최대 3분, 수가 바뀌면 새로 시작)

**▶ [최신 Windows 빌드 다운로드](https://github.com/wogur110/go-game/releases/latest)** — zip을 풀고
`BadukStudio.exe` 실행. 첫 실행 시 KataGo 엔진(기본 OpenCL)과 신경망을 앱에서 자동으로 받습니다.
([전체 릴리스 목록](https://github.com/wogur110/go-game/releases))

> 현재 상태: **M0–M4 완료.** 휴먼넷 급수별 대국 + 실시간 분석(승률·집수 바, 후보 오버레이,
> ownership 히트맵) + 두 번 패스 KataGo 집계산 + SGF 저장/로드 + **PyInstaller 패키징/GitHub Actions
> Windows 릴리스.** 적대적 다중 에이전트 리뷰로 버그 11건 수정. RTX 5060 Ti(Blackwell)+WSL2 검증.

## 개발 결정 (확정)

| 항목 | 선택 |
|---|---|
| 기술 스택 | Python + PySide6 (chess-game 구조 재사용) |
| 기본 엔진 | KataGo 28블록 `b28` (선택: b40 최강 / b18 빠름 / 휴먼넷) |
| GPU 백엔드 | NVIDIA CUDA/TensorRT (개발/실행은 WSL2 Linux) |
| 난이도 | 휴먼넷 급수별 (b28은 분석 전용 최강) |
| v1 범위 | Play 탭 — 대국 + 실시간 분석 오버레이 + SGF, 조이/포석 study는 v2 |
| 배포 | Windows 릴리스 + Linux 개발, 바이너리/가중치는 첫 실행 시 다운로드 |
| 규칙 | 19로 · 중국룰 · 코미 7.5 · 치석 지원 · 두 번 패스 후 KataGo 집계산 |

## 설치 / 첫 실행 (NVIDIA GPU)

CUDA/cuDNN을 따로 설치할 필요가 없습니다 — 필요한 런타임은 pip 휠로 들어오고, 엔진 실행
시 [app/engine/env.py](app/engine/env.py)가 `LD_LIBRARY_PATH`를 자동 구성합니다(수동 export 불필요).

```bash
pip install -r requirements.txt   # PySide6 + sgfmill + CUDA12 런타임(cudnn/cublas/cudart) 휠
python download_katago.py         # KataGo cuda12.8 빌드 + 네트워크(b28/b18/휴먼넷) 다운로드
python -m app.engine.smoke        # 엔진 연동 점검 (분석 + 휴먼넷 genmove)
python main.py --smoke            # 대국 통합 점검 (사람→AI 왕복, 헤드리스)
python main.py                    # GUI 실행 (사람 vs 휴먼넷 대국)
```

> conda 사용 시: `conda create -n go-game python=3.11 -y && conda run -n go-game pip install -r requirements.txt`,
> 이후 `conda run -n go-game python main.py`.

`download_katago.py`가 받는 것 (둘 다 git 미포함):
- 엔진 바이너리 → `engines/<os>/` (GitHub 릴리스 `v1.16.5`에서 OS/백엔드 에셋 자동 선택, 기본 `cuda12.8`)
- 네트워크 → `models/` : `b28`(기본·분석), `b18`(빠름), `b18c384nbt-humanv0`(휴먼넷·대국)

스모크가 통과하면(빈 판 분석 + 휴먼넷 첫 수) 엔진 연동 정상입니다. 첫 실행은 모델 로딩/GPU
초기화로 십수 초~수 분 걸릴 수 있습니다. (참고 실측: RTX 5060 Ti에서 ~21초)

> **다른 GPU/백엔드:** `--backend trt`(TensorRT 설치 필요), `--backend opencl`(OpenCL ICD 필요 —
> 기본 NVIDIA WSL 드라이버엔 없음), `--backend eigen`(CPU, 28블록엔 매우 느림). `--list`로 에셋 확인.
> Blackwell(RTX 50 시리즈)은 CUDA 12.8+ 빌드라야 동작합니다.

## 구조

```
download_katago.py        엔진 바이너리 + 네트워크 다운로더 (GitHub API로 에셋 자동 선택)
configs/
  analysis.cfg            KataGo analysis 엔진 설정 (승률 = 흑 기준 보고)
  gtp_human.cfg           KataGo GTP 휴먼넷 설정 (humanSLProfile = 급수)
app/
  engine/
    coords.py             내부 (x,y) ↔ GTP 좌표(A19, Q16 …) 변환
    types.py              MoveInfo / AnalysisResult 데이터 (흑 기준 승률·집수)
    networks.py           선택 가능한 네트워크 레지스트리 (b28 기본 · b40 최강 · b18 빠름, default_download 플래그)
    discovery.py          katago/네트워크/설정 파일 탐색 (PyInstaller·PATH 대응)
    analysis_client.py    `katago analysis` JSON 클라이언트 (분석 역할)
    gtp_client.py         `katago gtp` 휴먼넷 클라이언트 (대국 역할)
    smoke.py              헤드리스 엔진 연동 점검
```

## 엔진 연동 요약

체스의 **두 엔진(대국/분석)** 구조를 그대로 따릅니다:

- **분석** = `katago analysis -config configs/analysis.cfg -model models/<b28>` —
  위치마다 JSON 쿼리 1건을 보내고 `moveInfos`(승률·`scoreLead`·visits·pv)와
  `ownership`을 받습니다. 결과는 콜백으로 전달(M1에서 Qt 시그널로 GUI 스레드에 마샬링).
- **대국** = `katago gtp -model <b28> -human-model b18c384nbt-humanv0 -config gtp_human.cfg
  -override-config humanSLProfile=rank_5k` — `genmove`로 급수에 맞는 사람 같은 수를 둡니다.
  급수 변경 시 프로세스를 재시작합니다.

## 로드맵

- **M0 — 엔진 스파이크 ✅** : 다운로더, 분석/휴먼넷 클라이언트, 헤드리스 점검
- **M1 — 규칙 + 보드 + 대국 ✅** : 규칙 엔진(따냄/패/자살수/패스/집계산), 보드 위젯(렌더·클릭 착수),
  `GameController`(세대 카운터·Human/AI·undo·리뷰), Qt `EngineManager`, 사람↔휴먼넷 실제 대국
- **M2 — 분석 UI ✅** : 승률·집수 바, 후보수 오버레이, ownership 히트맵, 분석망 선택(b40/b28/b18 · 미보유 시 자동 다운로드), 사이드바(후보 패널·수순표)
- **M3 — 종국 처리 ✅** : 두 번 패스 후 KataGo `scoreLead` 집계산(사석은 ownership에 반영), SGF 저장/로드/리뷰
- **M4 — 패키징 ✅** : PyInstaller `baduk_studio.spec`(엔진 제외, 첫 실행 시 다운로드), `build_linux.sh`/`build_windows.bat`, GitHub Actions(우분투 테스트+빌드스모크 → 윈도우 빌드/릴리스)
- **인앱 엔진 다운로드 ✅** : 첫 실행 시 엔진이 없으면 백엔드 선택 + 진행률 다이얼로그로 다운로드
- **v2** : 조이(joseki)/포석(fuseki) study 탭

## 빌드 / 배포

```bash
./build_linux.sh            # dist/BadukStudio/BadukStudio (개발용)
# Windows: build_windows.bat → dist\BadukStudio\BadukStudio.exe
```

엔진(KataGo 바이너리 + 네트워크)은 용량/GPU 의존성 때문에 번들에 넣지 않고 **앱에서 받습니다**:

```bash
BadukStudio --download                 # 기본 백엔드: Windows=OpenCL, Linux=CUDA 12.8 (--backend 로 변경)
```

> **Windows 백엔드:** KataGo CUDA 빌드는 cudart/cublas/cudnn 등 ~1.3GB의 CUDA·cuDNN DLL을
> 따로 설치해야 동작합니다(미설치 시 `cublas64_12.dll 없음` 에러). 그래서 Windows 기본값은
> **OpenCL**(GPU 드라이버의 `OpenCL.dll`만 있으면 됨)입니다. CUDA를 쓰려면 CUDA 12 + cuDNN 9
> 런타임을 설치 후 `--backend cuda12.8`.

[.github/workflows/build.yml](.github/workflows/build.yml): main/PR/태그 push 시 우분투에서 규칙·SGF
테스트 + 엔진 없는 `--build-smoke`를 돌리고, windows-latest에서 exe를 빌드·스모크·zip 패키징하며,
`v*` 태그면 GitHub Release에 첨부합니다. (PyInstaller는 크로스컴파일 불가 → Windows exe는 Windows에서 빌드)
