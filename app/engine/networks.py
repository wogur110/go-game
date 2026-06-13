"""Registry of selectable KataGo networks.

The default is the 28-block network ("b28") for full-strength analysis. The
human-trained network powers rank-based, human-like opponents. Download URLs can
be overridden via ``KATAGO_<KEY>_URL`` environment variables (e.g.
``KATAGO_B28_URL``) — useful when a newer strongest network is published.

URLs verified 2026-06-13 (see the project memory). The b28/b18 networks come
from katagotraining.org; the human net is a KataGo v1.15.0 release asset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_KATA = "https://media.katagotraining.org/uploaded/networks/models/kata1"
_GH = "https://github.com/lightvector/KataGo/releases/download"


@dataclass(frozen=True)
class Network:
    key: str
    label: str
    filename: str
    url: str
    role: str   # "analysis" or "human"
    blocks: int


DEFAULT_NETWORK = "b28"
HUMAN_NETWORK = "human"

NETWORKS: dict[str, Network] = {
    "b28": Network(
        key="b28",
        label="KataGo 28블록 (기본 · 최강 분석)",
        filename="kata1-b28c512nbt-s13255194368-d5935380940.bin.gz",
        url=f"{_KATA}/kata1-b28c512nbt-s13255194368-d5935380940.bin.gz",
        role="analysis",
        blocks=28,
    ),
    "b18": Network(
        key="b18",
        label="KataGo 18블록 (더 빠름)",
        filename="kata1-b18c384nbt-s9131461376-d4087399203.bin.gz",
        url=f"{_KATA}/kata1-b18c384nbt-s9131461376-d4087399203.bin.gz",
        role="analysis",
        blocks=18,
    ),
    "human": Network(
        key="human",
        label="휴먼넷 (사람 모방 대국)",
        filename="b18c384nbt-humanv0.bin.gz",
        url=f"{_GH}/v1.15.0/b18c384nbt-humanv0.bin.gz",
        role="human",
        blocks=18,
    ),
}


def network_url(net: Network) -> str:
    """Resolved download URL, honouring a ``KATAGO_<KEY>_URL`` override."""
    return os.environ.get(f"KATAGO_{net.key.upper()}_URL", net.url)
