"""Disk admission for multipart spools and the map workflow's persisted copy.

All filesystem operations in this module are synchronous. Async callers must use
``asyncio.to_thread``; admission is bounded and never queues a GPU job.
"""

from __future__ import annotations

import errno
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException

MULTIPART_OVERHEAD_BYTES = 16 * 1024**2
MIN_FREE_BYTES = 512 * 1024**2


def insufficient_storage() -> HTTPException:
    return HTTPException(507, "上传临时目录或模型保存目录空间不足，请释放空间后重试")


def is_storage_exhaustion(error: BaseException) -> bool:
    """Recognize ENOSPC even when FastAPI wraps a spool error as HTTP 400."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, OSError) and error.errno in {errno.ENOSPC, errno.EDQUOT}:
            return True
        error = error.__cause__ or error.__context__
    return False


def _filesystem(path: Path) -> tuple[int, Path]:
    """Inspect the existing ancestor without creating or cleaning directories."""
    path = path.resolve()
    while not path.exists():
        path = path.parent
    if not path.is_dir():
        raise NotADirectoryError(str(path))
    return path.stat().st_dev, path


@dataclass
class StorageReservation:
    budget: StorageBudget
    amounts: dict[int, int]
    released: bool = field(default=False, init=False)

    def release(self) -> None:
        with self.budget.lock:
            if self.released:
                return
            for device, amount in self.amounts.items():
                remaining = self.budget.reserved[device] - amount
                if remaining:
                    self.budget.reserved[device] = remaining
                else:
                    del self.budget.reserved[device]
            self.released = True


class StorageBudget:
    """Process-local admission prevents concurrent requests spending one budget.

    Temporary and persisted copies on one device are summed before checking one
    free-space sample. The fixed margin is charged once per device, not per path.
    This is an admission check, not a disk quota against unrelated processes.
    """

    def __init__(self, min_free_bytes: int = MIN_FREE_BYTES):
        self.min_free_bytes = min_free_bytes
        self.lock = threading.Lock()
        self.reserved: dict[int, int] = {}

    def reserve(self, temp_root: Path, local_root: Path, temp_bytes: int, persistent_bytes: int) -> StorageReservation:
        with self.lock:
            amounts: dict[int, int] = {}
            paths: dict[int, Path] = {}
            try:
                for root, amount in ((temp_root, temp_bytes), (local_root, persistent_bytes)):
                    device, existing = _filesystem(root)
                    amounts[device] = amounts.get(device, 0) + amount
                    paths.setdefault(device, existing)
                for device, amount in amounts.items():
                    if shutil.disk_usage(paths[device]).free < amount + self.reserved.get(device, 0) + self.min_free_bytes:
                        raise insufficient_storage()
            except OSError:
                raise insufficient_storage() from None
            for device, amount in amounts.items():
                self.reserved[device] = self.reserved.get(device, 0) + amount
            return StorageReservation(self, amounts)


def require_persistent_space(local_root: Path, required_bytes: int) -> None:
    """Recheck actual copy size immediately before a persistent write.

    This check intentionally does not acquire a second admission reservation for
    the same request. Call it inside an existing worker-thread copy operation.
    """
    try:
        _, existing = _filesystem(local_root)
        if shutil.disk_usage(existing).free < required_bytes + MIN_FREE_BYTES:
            raise insufficient_storage()
    except OSError:
        raise insufficient_storage() from None
