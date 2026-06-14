"""Download the KataGo engine binary and neural-net weights (one-time setup).

The app is otherwise offline; these artifacts are too big for git so they live in
``engines/`` and ``models/`` (both git-ignored).

Examples:
    python download_katago.py                     # current OS, CUDA 12.8 backend + all networks
    python download_katago.py --backend trt       # NVIDIA TensorRT build (needs TensorRT installed)
    python download_katago.py --backend opencl    # portable GPU build (needs an OpenCL ICD)
    python download_katago.py --networks-only     # just the .bin.gz weights
    python download_katago.py --list              # list downloadable engine assets

Backend notes — the default is OS-aware:
- **Windows → opencl**: the KataGo Windows CUDA build needs ~1.3GB of CUDA/cuDNN
  DLLs (cudart/cublas/cublasLt/cudnn) that aren't bundled, whereas the OpenCL
  build runs on just the GPU driver's OpenCL.dll. So OpenCL is the safe default.
  (Use ``--backend cuda12.8`` only if you've installed the CUDA 12 + cuDNN 9 runtime.)
- **Linux → cuda12.8**: satisfied by the ``nvidia-*-cu12`` pip wheels in
  requirements.txt (no system CUDA/cuDNN install, no manual LD_LIBRARY_PATH).
  Verified on an RTX 50-series (Blackwell) GPU in WSL2.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from app.engine.networks import NETWORKS, network_url

KATAGO_RELEASE = "v1.16.5"
API_URL = f"https://api.github.com/repos/lightvector/KataGo/releases/tags/{KATAGO_RELEASE}"

# Map a friendly backend name to the substring that identifies the release asset.
BACKENDS = {
    "opencl": "opencl",
    "cuda12.8": "cuda12.8",
    "cuda12.5": "cuda12.5",
    "cuda12.1": "cuda12.1",
    "trt": "trt10.9.0",
    "trt10.9": "trt10.9.0",
    "trt10.2": "trt10.2.0",
    "trt8.6": "trt8.6.1",
    "eigen": "-eigen-",       # plain CPU build (no AVX2)
    "eigenavx2": "eigenavx2",  # faster CPU build
}
DEFAULT_BACKEND = "cuda12.8"


def default_backend() -> str:
    """OS-aware default. On Windows the CUDA build needs ~1.3GB of CUDA/cuDNN
    DLLs the user doesn't have, while the OpenCL build runs on just the GPU
    driver's OpenCL.dll — so default to OpenCL there. On Linux the CUDA build is
    satisfied by the nvidia-*-cu12 pip wheels (see requirements.txt)."""
    return "opencl" if os.name == "nt" else "cuda12.8"


# Exact asset-name middle tokens for KATAGO_RELEASE, so the binary can be fetched
# by a DIRECT release URL without the GitHub API (whose unauthenticated 60/hour
# limit otherwise causes "HTTP Error 403: rate limit exceeded").
ASSET_STEMS = {
    "opencl": "opencl",
    "cuda12.8": "cuda12.8-cudnn9.8.0",
    "cuda12.5": "cuda12.5-cudnn8.9.7",
    "cuda12.1": "cuda12.1-cudnn8.9.7",
    "trt": "trt10.9.0-cuda12.8",
    "trt10.9": "trt10.9.0-cuda12.8",
    "trt10.2": "trt10.2.0-cuda12.5",
    "trt8.6": "trt8.6.1-cuda12.1",
    "eigen": "eigen",
    "eigenavx2": "eigenavx2",
}


def direct_asset_name(os_name: str, backend: str, bs50: bool) -> str | None:
    stem = ASSET_STEMS.get(backend)
    if not stem:
        return None
    os_tok = "windows-x64" if os_name == "windows" else "linux-x64"
    return f"katago-{KATAGO_RELEASE}-{stem}-{os_tok}{'+bs50' if bs50 else ''}.zip"


def release_download_url(name: str) -> str:
    return f"https://github.com/lightvector/KataGo/releases/download/{KATAGO_RELEASE}/{name}"


class Cancelled(Exception):
    """Raised inside a download loop when ``should_cancel()`` turns True, so the
    GUI can stop a long fetch (e.g. the 823MB b40 net) without killing the thread."""

# Write next to the executable when frozen (PyInstaller), so a packaged build
# downloads engines/ and models/ beside the app rather than into a temp dir.
ROOT = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent)


def _ua_request(url: str) -> urllib.request.Request:
    headers = {"User-Agent": "baduk-studio-setup"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:        # only the API path is rate-limited
        headers["Authorization"] = f"token {token}"
    return urllib.request.Request(url, headers=headers)


def download_stream(url: str, dest: Path, on_progress=None, should_cancel=None) -> None:
    """Download ``url`` to ``dest``. ``on_progress(message, fraction)`` is called
    for GUI use (fraction in [0,1], or -1 when unknown). ``should_cancel()`` is
    polled between chunks; when it returns True we drop the partial file and raise
    :class:`Cancelled` so a GUI thread can stop cleanly."""
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"  [skip] {dest.name} 이미 존재")
        if on_progress:
            on_progress(f"{dest.name} 이미 있음", 1.0)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".part")
    print(f"  [get ] {url}")
    last_pct = -1
    try:
        with urllib.request.urlopen(_ua_request(url)) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            got = 0
            with open(tmp, "wb") as fh:
                while True:
                    if should_cancel and should_cancel():
                        raise Cancelled()
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if total:
                        pct = got * 100 // total
                        print(f"\r  [....] {pct:3d}%  {got >> 20} / {total >> 20} MB", end="")
                        if on_progress and pct != last_pct:
                            last_pct = pct
                            on_progress(f"{dest.name}  {got >> 20} / {total >> 20} MB", got / total)
            print()
        tmp.replace(dest)
    except Cancelled:
        tmp.unlink(missing_ok=True)
        raise
    print(f"  [ok  ] {dest} ({dest.stat().st_size >> 20} MB)")
    if on_progress:
        on_progress(f"{dest.name} 완료", 1.0)


def fetch_assets() -> list[dict]:
    with urllib.request.urlopen(_ua_request(API_URL)) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("assets", [])


def resolve_asset(assets: list[dict], os_name: str, backend: str, bs50: bool) -> dict | None:
    token = BACKENDS[backend]
    os_token = "windows-x64" if os_name == "windows" else "linux-x64"
    cands = [
        a for a in assets
        if token in a["name"] and os_token in a["name"]
        and a["name"].endswith((".zip", ".tar.gz"))
        and (("+bs50" in a["name"]) == bs50)
    ]
    return cands[0] if cands else None


def download_binary(os_name: str, backend: str, bs50: bool, on_progress=None,
                    should_cancel=None) -> None:
    print(f"\nKataGo {KATAGO_RELEASE} 바이너리 ({os_name}, {backend})")
    # Prefer a direct release URL (no GitHub API → no rate limit). Fall back to the
    # API only for an unknown backend not in ASSET_STEMS.
    name = direct_asset_name(os_name, backend, bs50)
    url = release_download_url(name) if name else None
    if not url:
        if on_progress:
            on_progress("에셋 정보 조회…", -1)
        asset = resolve_asset(fetch_assets(), os_name, backend, bs50)
        if not asset:
            print("  ✗ 일치하는 에셋 없음. --list 로 확인하세요.")
            raise RuntimeError(f"'{backend}' 백엔드용 {os_name} 에셋을 찾지 못했습니다")
        name, url = asset["name"], asset["browser_download_url"]

    dest_dir = ROOT / "engines" / os_name
    archive_path = dest_dir / name
    download_stream(url, archive_path, on_progress, should_cancel)

    if on_progress:
        on_progress("엔진 압축 해제 중…", -1)
    print(f"  [unzip] {name} → engines/{os_name}/")
    payload = archive_path.read_bytes()
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            z.extractall(dest_dir)
    else:
        with tarfile.open(fileobj=io.BytesIO(payload)) as t:
            t.extractall(dest_dir)
    archive_path.unlink(missing_ok=True)

    exe = "katago.exe" if os_name == "windows" else "katago"
    found = next((p for p in dest_dir.rglob(exe) if p.is_file()), None)
    if not found:
        print(f"  ⚠ 압축은 풀렸으나 {exe} 를 찾지 못했습니다: engines/{os_name}/ 확인")
        return
    if os_name != "windows":
        found.chmod(0o755)
    print(f"  [ok  ] {found}")


def download_networks(only: str | None = None, on_progress=None, should_cancel=None) -> None:
    print("\nKataGo 네트워크 (가중치)")
    models = ROOT / "models"
    for key, net in NETWORKS.items():
        if only and key != only:
            continue
        if only is None and not net.default_download:
            continue   # opt-in network (e.g. b40) — only fetched when explicitly selected
        if on_progress:
            on_progress(f"네트워크 {net.filename}", -1)
        download_stream(network_url(net), models / net.filename, on_progress, should_cancel)


def download_all(backend: str | None = None, os_name: str | None = None,
                 bs50: bool = False, on_progress=None,
                 networks: bool = True, binary: bool = True,
                 should_cancel=None) -> None:
    """Programmatic entry (used by the in-app download dialog)."""
    if backend is None:
        backend = default_backend()
    if os_name is None:
        os_name = "windows" if os.name == "nt" else "linux"
    if networks:
        download_networks(None, on_progress=on_progress, should_cancel=should_cancel)
    if binary:
        download_binary(os_name, backend, bs50, on_progress=on_progress,
                        should_cancel=should_cancel)
    if on_progress:
        on_progress("완료", 1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", choices=sorted(BACKENDS), default=default_backend())
    parser.add_argument("--os", dest="os_name", choices=["linux", "windows"],
                        default=("windows" if os.name == "nt" else "linux"))
    parser.add_argument("--bs50", action="store_true",
                        help="larger max-batch-size engine build")
    parser.add_argument("--networks-only", action="store_true")
    parser.add_argument("--binary-only", action="store_true")
    parser.add_argument("--network", choices=sorted(NETWORKS),
                        help="download only this one network")
    parser.add_argument("--list", action="store_true",
                        help="list engine assets for the release and exit")
    args = parser.parse_args()

    if args.list:
        for a in fetch_assets():
            if a["name"].endswith((".zip", ".tar.gz")):
                print(a["name"])
        return 0

    if not args.binary_only:
        download_networks(args.network)
    if not args.networks_only:
        download_binary(args.os_name, args.backend, args.bs50)

    print("\n완료. 점검:  python -m app.engine.smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
