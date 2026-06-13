"""Download the KataGo engine binary and neural-net weights (one-time setup).

The app is otherwise offline; these artifacts are too big for git so they live in
``engines/`` and ``models/`` (both git-ignored).

Examples:
    python download_katago.py                     # current OS, CUDA 12.8 backend + all networks
    python download_katago.py --backend trt       # NVIDIA TensorRT build (needs TensorRT installed)
    python download_katago.py --backend opencl    # portable GPU build (needs an OpenCL ICD)
    python download_katago.py --networks-only     # just the .bin.gz weights
    python download_katago.py --list              # list downloadable engine assets

Backend notes (NVIDIA): the default is **cuda12.8** — verified on an RTX 50-series
(Blackwell) GPU in WSL2. Its CUDA/cuDNN runtime is supplied by the ``nvidia-*-cu12``
pip wheels in requirements.txt, so ``pip install -r requirements.txt`` is all you
need (no system CUDA/cuDNN install, no manual LD_LIBRARY_PATH). ``opencl`` needs an
OpenCL ICD (absent from the default NVIDIA WSL driver); ``trt`` needs TensorRT.
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

ROOT = Path(__file__).resolve().parent


def _ua_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": "baduk-studio-setup"})


def download_stream(url: str, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"  [skip] {dest.name} 이미 존재")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".part")
    print(f"  [get ] {url}")
    with urllib.request.urlopen(_ua_request(url)) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        got = 0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                if total:
                    pct = got * 100 // total
                    print(f"\r  [....] {pct:3d}%  {got >> 20} / {total >> 20} MB", end="")
        print()
    tmp.replace(dest)
    print(f"  [ok  ] {dest} ({dest.stat().st_size >> 20} MB)")


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


def download_binary(os_name: str, backend: str, bs50: bool) -> None:
    print(f"\nKataGo {KATAGO_RELEASE} 바이너리 ({os_name}, {backend})")
    assets = fetch_assets()
    asset = resolve_asset(assets, os_name, backend, bs50)
    if not asset:
        print(f"  ✗ 일치하는 에셋 없음. --list 로 확인하세요.")
        raise SystemExit(2)
    dest_dir = ROOT / "engines" / os_name
    archive_path = dest_dir / asset["name"]
    download_stream(asset["browser_download_url"], archive_path)

    print(f"  [unzip] {asset['name']} → engines/{os_name}/")
    payload = archive_path.read_bytes()
    if asset["name"].endswith(".zip"):
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


def download_networks(only: str | None = None) -> None:
    print("\nKataGo 네트워크 (가중치)")
    models = ROOT / "models"
    for key, net in NETWORKS.items():
        if only and key != only:
            continue
        download_stream(network_url(net), models / net.filename)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", choices=sorted(BACKENDS), default=DEFAULT_BACKEND)
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
