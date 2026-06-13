"""Build the environment KataGo's CUDA build needs, so the app "just works"
without the user exporting ``LD_LIBRARY_PATH`` by hand.

The ``cuda12.8`` KataGo build dynamically links ``libcudnn.so.9``,
``libcublas.so.12``, ``libcudart.so.12`` etc. We satisfy these from the
``nvidia-*-cu12`` pip wheels (see requirements.txt) plus the WSL/Linux NVIDIA
driver libs, and prepend their directories to ``LD_LIBRARY_PATH`` for the
spawned engine process only. On Windows the needed DLLs ship inside the engine
archive, so this is a no-op there.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import List

# Extra system locations to probe (CUDA toolkit + WSL driver libs).
_SYSTEM_LIB_DIRS = (
    "/usr/lib/wsl/lib",          # WSL: libcuda.so (NVIDIA driver)
    "/usr/local/cuda/lib64",     # CUDA toolkit (symlink to current)
)


def _nvidia_wheel_lib_dirs() -> List[str]:
    """Lib dirs of any installed ``nvidia-*-cu12`` pip wheels (cudnn, cublas, ...)."""
    spec = importlib.util.find_spec("nvidia")
    if not spec or not spec.submodule_search_locations:
        return []
    root = Path(list(spec.submodule_search_locations)[0])
    dirs: List[str] = []
    for sub in sorted(root.iterdir()):
        lib = sub / "lib"
        if lib.is_dir():
            dirs.append(str(lib))
    return dirs


def engine_env() -> dict:
    """A copy of ``os.environ`` with ``LD_LIBRARY_PATH`` augmented for KataGo (Linux)."""
    env = dict(os.environ)
    if os.name == "nt":
        return env
    extra: List[str] = list(_nvidia_wheel_lib_dirs())
    for cand in _SYSTEM_LIB_DIRS:
        if Path(cand).is_dir():
            extra.append(cand)
    if extra:
        prev = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ":".join(extra + ([prev] if prev else []))
    return env
