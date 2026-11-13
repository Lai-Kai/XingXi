"""Configure this host's existing OOOSplat engines for the map Gateway.

Run with the deployment owner's Python, after installing the reconstruction extra.
Creates a dedicated loopback SSH key; never copies a user's login password.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def write_private(path: Path, value: str) -> None:
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlink: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".map-setup-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600) if hasattr(os, "fchmod") else None
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def authorize_key(path: Path, public_key: str) -> None:
    parts = public_key.split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("Expected an Ed25519 public key")
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if not any(parts[1] in line.split() for line in old.splitlines()):
        line = f'from="127.0.0.1",restrict {parts[0]} {parts[1]} xingxi-map-loopback\n'
        write_private(
            path, old + ("\n" if old and not old.endswith("\n") else "") + line
        )


def update_env(path: Path, settings: dict[str, str]) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    start, end = "# BEGIN XINGXI MAP WORKER", "# END XINGXI MAP WORKER"
    pattern = re.compile(
        r"^(?:export\s+)?(" + "|".join(re.escape(k) for k in settings) + r")\s*="
    )
    kept, in_block = [], False
    for line in old.splitlines(keepends=True):
        if line.strip() == start:
            in_block = True
        elif line.strip() == end:
            in_block = False
        elif not in_block and not pattern.match(line):
            kept.append(line)
    prefix = "".join(kept).rstrip("\n")
    block = "\n".join(
        [start, *(f"{key}={value}" for key, value in settings.items()), end]
    )
    write_private(path, prefix + ("\n\n" if prefix else "") + block + "\n")


def ssh_settings(user: str, key: Path) -> dict:
    return {"host": "127.0.0.1", "port": 22, "user": user, "key_filename": str(key)}


def main() -> None:
    import fcntl
    import pwd
    import paramiko

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--engine-dir", type=Path, default=Path("/data/yuyuan/ooosplat/engines")
    )
    parser.add_argument(
        "--executable", type=Path, default=Path("/data/yuyuan/ooosplat/bin/splatstudio")
    )
    parser.add_argument("--flux-root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.stat().st_uid != os.geteuid():
        raise SystemExit("Run this script as the source checkout owner, not root.")
    user = pwd.getpwuid(os.geteuid()).pw_name
    home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    for engine in [
        args.executable,
        *(
            args.engine_dir / name
            for name in ("colmap", "brush_app", "ffmpeg", "ffprobe")
        ),
    ]:
        if not os.access(engine, os.X_OK):
            raise SystemExit("Engine is not executable: " + str(engine))
    worker = root / "backend/.deer-flow/reconstruction-worker"
    worker.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (worker / "setup.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ssh = worker / "ssh"
        ssh.mkdir(exist_ok=True, mode=0o700)
        jobs = worker / "jobs"
        jobs.mkdir(exist_ok=True, mode=0o700)
        key = ssh / "id_ed25519"
        if not key.exists():
            subprocess.run(
                [
                    "ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "xingxi-map-loopback",
                    "-f",
                    str(key),
                ],
                check=True,
            )
        key.chmod(0o600)
        ssh.chmod(0o700)
        public = key.with_suffix(".pub").read_text(encoding="utf-8")
        (home / ".ssh").mkdir(exist_ok=True, mode=0o700)
        authorize_key(home / ".ssh/authorized_keys", public)
        # Local host public key is read from the OS, never learned via AutoAddPolicy.
        host = Path("/etc/ssh/ssh_host_ed25519_key.pub").read_text().split()
        hosts = ssh / "known_hosts"
        write_private(hosts, "127.0.0.1 " + " ".join(host[:2]) + "\n")
        config = ssh / "connection.json"
        write_private(config, json.dumps(ssh_settings(user, key)) + "\n")
        client = paramiko.SSHClient()
        client.load_host_keys(str(hosts))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                "127.0.0.1",
                username=user,
                key_filename=str(key),
                allow_agent=False,
                look_for_keys=False,
                timeout=10,
                auth_timeout=10,
            )
            with client.open_sftp() as sftp:
                sftp.stat(str(jobs))
            _, out, _ = client.exec_command(
                "test -x " + shlex.quote(str(args.executable)), timeout=10
            )
            if out.channel.recv_exit_status() != 0:
                raise RuntimeError("SSH worker cannot access OOOSplat")
        finally:
            client.close()
        values = {
            "XINGXI_OOOSPLAT_SSH_CONFIG": str(config),
            "XINGXI_OOOSPLAT_KNOWN_HOSTS": str(hosts),
            "XINGXI_OOOSPLAT_REMOTE_ROOT": str(jobs),
            "XINGXI_OOOSPLAT_EXECUTABLE": str(args.executable),
            "XINGXI_OOOSPLAT_ENGINE_DIR": str(args.engine_dir),
        }
        if args.flux_root:
            flux = args.flux_root.resolve()
            if not os.access(flux / "data/input/xingxi", os.W_OK) or not os.access(
                flux / "data/output/xingxi", os.R_OK | os.X_OK
            ):
                raise SystemExit(
                    "FLUX input/xingxi needs write permission and output/xingxi needs read/traverse permission."
                )
            values.update(
                XINGXI_FLUX3_DEPLOY_ROOT=str(flux),
                XINGXI_FLUX3_BASE_URL="http://127.0.0.1:18188",
                XINGXI_FLUX3_PYTHON=str(flux / ".venv/bin/python"),
            )
        update_env(root / ".env", values)
    print(
        json.dumps(
            {
                "configured": True,
                "worker_user": user,
                "transport": "SSH/SFTP loopback",
                "flux3": bool(args.flux_root),
            }
        )
    )
    print(
        "Restart the existing Gateway using its deployment launcher to load these settings."
    )


if __name__ == "__main__":
    main()
