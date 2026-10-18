from __future__ import annotations

import importlib.util
import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from deerflow.config.runtime_paths import runtime_home

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
TERMINAL = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class ReconstructionConfig:
    local_root: Path = field(default_factory=lambda: runtime_home() / "reconstructions")
    ssh_config: Path = field(default_factory=lambda: Path(os.getenv("XINGXI_OOOSPLAT_SSH_CONFIG", str(Path(os.getenv("DEER_FLOW_PROJECT_ROOT", Path(__file__).resolve().parents[4])) / ".cache" / "server_ssh.json"))))
    remote_root: str = field(default_factory=lambda: os.getenv("XINGXI_OOOSPLAT_REMOTE_ROOT", "/data/yuyuan/ooosplat/workspace/xingxi_jobs"))
    executable: str = field(default_factory=lambda: os.getenv("XINGXI_OOOSPLAT_EXECUTABLE", "/data/yuyuan/ooosplat/bin/splatstudio"))
    flux3_root: str = field(default_factory=lambda: os.getenv("XINGXI_FLUX3_DEPLOY_ROOT", ""))
    flux3_url: str = field(default_factory=lambda: os.getenv("XINGXI_FLUX3_BASE_URL", "http://127.0.0.1:18188"))

    @property
    def flux3_enabled(self) -> bool:
        return bool(self.flux3_root.startswith("/"))

    def flux3_snapshot(self) -> dict:
        return {
            "deploy_root": self.flux3_root,
            "base_url": self.flux3_url,
            "python": os.getenv("XINGXI_FLUX3_PYTHON", self.flux3_root + "/.venv/bin/python"),
            "engine_dir": os.getenv("XINGXI_OOOSPLAT_ENGINE_DIR", posixpath.normpath(posixpath.dirname(self.executable) + "/../engines")),
        }

    max_bytes: int = 2 * 1024**3
    max_files: int = 500

    @property
    def known_hosts(self) -> Path:
        return Path(os.getenv("XINGXI_OOOSPLAT_KNOWN_HOSTS", str(self.local_root / "known_hosts")))

    @property
    def enabled(self) -> bool:
        return self.ssh_config.is_file() and self.known_hosts.is_file() and importlib.util.find_spec("paramiko") is not None
