"""Production Docker PostgreSQL integration contract."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OVERLAY_PATH = REPO_ROOT / "docker" / "docker-compose.postgres.yaml"


def _bash_executable() -> str:
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_bash = Path(git).resolve().parent.parent / "bin" / "bash.exe"
            if git_bash.exists():
                return str(git_bash)
    return shutil.which("bash") or "bash"


def test_postgres_overlay_provides_healthy_persistent_database_for_gateway():
    compose = yaml.safe_load(OVERLAY_PATH.read_text(encoding="utf-8"))

    postgres = compose["services"]["postgres"]
    assert postgres["image"] == "pgvector/pgvector:0.8.1-pg17-bookworm"
    assert postgres["volumes"] == [
        {
            "type": "volume",
            "source": "postgres-data",
            "target": "/var/lib/postgresql/data",
            "volume": {"nocopy": True},
        }
    ]
    assert postgres["healthcheck"]["test"] == ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]

    gateway = compose["services"]["gateway"]
    assert gateway["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}" in gateway["environment"]
    assert "postgres-data" in compose["volumes"]


def test_production_services_have_healthchecks_and_healthy_dependencies():
    compose = yaml.safe_load((REPO_ROOT / "docker" / "docker-compose.yaml").read_text(encoding="utf-8"))

    assert compose["services"]["redis"]["volumes"] == [
        {
            "type": "volume",
            "source": "redis-data",
            "target": "/data",
            "volume": {"nocopy": True},
        }
    ]
    for service_name in ("redis", "frontend", "gateway", "nginx"):
        assert "healthcheck" in compose["services"][service_name], service_name

    nginx_dependencies = compose["services"]["nginx"]["depends_on"]
    assert nginx_dependencies["frontend"]["condition"] == "service_healthy"
    assert nginx_dependencies["gateway"]["condition"] == "service_healthy"

    gateway_dependencies = compose["services"]["gateway"]["depends_on"]
    assert gateway_dependencies["redis"]["condition"] == "service_healthy"


def test_production_deploy_activates_postgres_overlay_and_service(tmp_path):
    worktree = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", worktree / "scripts")
    shutil.copytree(REPO_ROOT / "docker", worktree / "docker")
    (worktree / "backend").mkdir()
    (worktree / "config.yaml").write_text(
        "database:\n  backend: postgres\n  postgres_url: $DATABASE_URL\n",
        encoding="utf-8",
    )
    (worktree / "extensions_config.json").write_text('{"mcpServers":{},"skills":{}}\n', encoding="utf-8")
    (worktree / ".env").write_text(
        "POSTGRES_USER=deerflow\nPOSTGRES_PASSWORD=test-password\nPOSTGRES_DB=deerflow\nPORT=12026\nBIND_ADDRESS=127.0.0.1\n",
        encoding="utf-8",
    )

    capture = tmp_path / "docker-args.txt"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        '#!/usr/bin/env sh\nfor arg in "$@"; do printf "%s\\n" "$arg"; done > "$CAPTURE_DOCKER_ARGS"\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)

    env = os.environ.copy()
    env["CAPTURE_DOCKER_ARGS"] = str(capture)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [_bash_executable(), str(worktree / "scripts" / "deploy.sh"), "start"],
        cwd=worktree,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr

    args = capture.read_text(encoding="utf-8").splitlines()
    assert any(arg.replace("\\", "/").endswith("/docker/docker-compose.postgres.yaml") for arg in args)
    assert "postgres" in args
    assert "http://localhost:12026" in result.stdout


def test_postgres_deploy_generates_and_exports_persistent_password(tmp_path):
    worktree = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", worktree / "scripts")
    shutil.copytree(REPO_ROOT / "docker", worktree / "docker")
    (worktree / "backend").mkdir()
    (worktree / "config.yaml").write_text(
        "database:\n  backend: postgres\n  postgres_url: $DATABASE_URL\n",
        encoding="utf-8",
    )
    (worktree / "extensions_config.json").write_text('{"mcpServers":{},"skills":{}}\n', encoding="utf-8")

    capture = tmp_path / "postgres-password.txt"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        '#!/usr/bin/env sh\nprintf "%s" "${POSTGRES_PASSWORD:-}" > "$CAPTURE_POSTGRES_PASSWORD"\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)

    env = os.environ.copy()
    env.pop("POSTGRES_PASSWORD", None)
    env["CAPTURE_POSTGRES_PASSWORD"] = str(capture)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [_bash_executable(), str(worktree / "scripts" / "deploy.sh"), "start"],
        cwd=worktree,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr

    secret = (worktree / "backend" / ".deer-flow" / ".postgres-password").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"[0-9a-f]{64}", secret)
    assert capture.read_text(encoding="utf-8") == secret


def test_postgres_deploy_rejects_missing_postgres_url(tmp_path):
    worktree = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", worktree / "scripts")
    shutil.copytree(REPO_ROOT / "docker", worktree / "docker")
    (worktree / "backend").mkdir()
    (worktree / "config.yaml").write_text("database:\n  backend: postgres\n", encoding="utf-8")
    (worktree / "extensions_config.json").write_text('{"mcpServers":{},"skills":{}}\n', encoding="utf-8")
    (worktree / ".env").write_text(
        "POSTGRES_USER=deerflow\nPOSTGRES_PASSWORD=test-password\nPOSTGRES_DB=deerflow\n",
        encoding="utf-8",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text('#!/usr/bin/env sh\nexit 0\n', encoding="utf-8")
    docker.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [_bash_executable(), str(worktree / "scripts" / "deploy.sh"), "start"],
        cwd=worktree,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode != 0
    assert "database.postgres_url" in result.stderr
