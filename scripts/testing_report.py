"""Run existing test commands and keep honest, per-batch evidence on failure."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def redact(text: str) -> str:
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s\"\']+", r"\1[REDACTED]", text
    )
    return re.sub(
        r"(?i)((?:api[_-]?key|password|secret|access_token)\s*[=:]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )


def artifact_counts(output: Path) -> dict | None:
    """Preserve reporter counts; unknown or missing counts stay unavailable."""
    if (output / "junit.xml").is_file():
        suites = ElementTree.parse(output / "junit.xml").getroot()
        cases = list(suites.iter("testcase"))
        return {
            "total": len(cases),
            "failed": sum(case.find("failure") is not None for case in cases),
            "error": sum(case.find("error") is not None for case in cases),
            "skipped": sum(case.find("skipped") is not None for case in cases),
        }
    if (output / "results.json").is_file():
        report = json.loads((output / "results.json").read_text(encoding="utf-8"))
        if "numTotalTests" in report:
            return {
                key: report.get(source)
                for key, source in {
                    "total": "numTotalTests",
                    "passed": "numPassedTests",
                    "failed": "numFailedTests",
                    "skipped": "numPendingTests",
                }.items()
            }
        if "stats" in report:
            return report["stats"]
    return None


def run_check(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    output: Path,
    required: list[str],
    timeout: int,
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    environment = {
        **os.environ,
        "TEST_REPORT_DIR": str(output.resolve()),
        "PYTHONIOENCODING": "utf-8",
    }
    result = {
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "started_at": datetime.now(UTC).isoformat(),
    }
    # Spool output to disk so a large test run cannot exhaust the report process.
    raw = output / "command.raw"
    try:
        with raw.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix",
            )
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
                raise
        result.update(
            exit_code=process.returncode,
            status="passed"
            if process.returncode == 0
            else ("failed" if process.returncode == 1 else "error"),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.update(
            exit_code=None, status="error", error=f"{type(exc).__name__}: {exc}"
        )
    if raw.exists():
        with (
            raw.open(encoding="utf-8", errors="replace") as source,
            (output / "command.log").open("w", encoding="utf-8") as destination,
        ):
            for line in source:
                destination.write(redact(line))
        raw.unlink()
    missing = [name for name in required if not (output / name).is_file()]
    result.update(
        elapsed_seconds=round(time.monotonic() - started, 3), missing_artifacts=missing
    )
    if missing:
        result.update(
            status="error",
            error=result.get("error") or "Required test artifacts were not generated",
        )
    try:
        result["counts"] = artifact_counts(output)
        if result["counts"] and result["counts"].get("error", 0):
            result.update(
                status="error",
                error=result.get("error")
                or "Test reporter recorded collection or execution errors",
            )
    except (ValueError, ElementTree.ParseError) as exc:
        result.update(
            status="error", error=f"Invalid test artifact: {exc}", counts=None
        )
    return result


def write_summary(directory: Path, checks: list[dict], *, environment: dict) -> None:
    result = {
        "batch_id": directory.name,
        "created_at": datetime.now(UTC).isoformat(),
        "environment": environment,
        "checks": checks,
    }
    (directory / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 星羲软件测试记录",
        "",
        f"批次：{directory.name}",
        "",
        "| 检查 | 状态 | 退出码 | 耗时 s | 原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    cards = []
    for check in checks:
        reason = check.get("error", "") or (
            "缺少产物：" + ", ".join(check["missing_artifacts"])
            if check["missing_artifacts"]
            else ""
        )
        lines.append(
            f"| {check['name']} | {check['status']} | {check['exit_code']} | {check['elapsed_seconds']} | {html.escape(reason).replace('|', '/')} |"
        )
        name = html.escape(check["name"])
        links = [f'<a href="{name}/command.log">日志</a>']
        if (directory / check["name"] / "playwright-report/index.html").exists():
            links.append(
                f'<a href="{name}/playwright-report/index.html">浏览器报告与回放</a>'
            )
        cards.append(
            f"<section><h2>{name} · {html.escape(check['status'])}</h2><p>{html.escape(reason)}</p><p>计数：{html.escape(str(check.get('counts') or '未取得结果'))}</p><p>{' · '.join(links)}</p><pre>{html.escape(' '.join(check['command']))}</pre></section>"
        )
    lines.extend(
        [
            "",
            "后端/前端单元测试验证软件逻辑；browser 使用模拟后端；replay 使用真实 Gateway 与固定模型。均不代表真实模型质量评测。",
            "",
            "## 环境",
            "",
            "```json",
            json.dumps(environment, ensure_ascii=False, indent=2),
            "```",
        ]
    )
    (directory / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (directory / "index.html").write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>星羲软件测试记录</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px;background:#f7fafb;color:#203438}section{padding:20px;margin:15px 0;background:white;border:1px solid #ccdadd;border-radius:8px}pre{white-space:pre-wrap}</style><h1>星羲软件测试记录</h1><p>真实命令与产物；未执行和缺失报告不会计为通过。</p>'
        + "".join(cards)
        + "</html>",
        encoding="utf-8",
    )
    files = [
        {
            "path": str(path.relative_to(directory)),
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    ]
    (directory / "manifest.json").write_text(
        json.dumps(
            {"batch_id": directory.name, "environment": environment, "files": files},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=["backend", "frontend", "browser", "replay"],
        default=["backend", "frontend", "browser", "replay"],
    )
    parser.add_argument("--output", type=Path, default=ROOT / "reports/testing")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    directory = (
        args.output.resolve()
        / f"software-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    )
    directory.mkdir(parents=True, exist_ok=False)
    python = (
        str(ROOT / "backend/.venv/bin/python")
        if (ROOT / "backend/.venv/bin/python").is_file()
        else sys.executable
    )
    pnpm = shutil.which("pnpm")
    frontend = (
        [pnpm, "exec"] if pnpm else [str(ROOT / "frontend/node_modules/.bin") + "/"]
    )

    def js(tool):
        return (
            [*frontend, tool]
            if pnpm
            else [str(ROOT / "frontend/node_modules/.bin" / tool)]
        )

    commands = {
        "backend": (
            [
                python,
                "-m",
                "pytest",
                "tests/",
                "-q",
                f"--junitxml={directory}/backend/junit.xml",
            ],
            ROOT / "backend",
            ["junit.xml"],
        ),
        "frontend": ([*js("rstest"), "run"], ROOT / "frontend", ["results.json"]),
        "browser": (
            [*js("playwright"), "test"],
            ROOT / "frontend",
            ["results.json", "playwright-report/index.html"],
        ),
        "replay": (
            [*js("playwright"), "test", "-c", "playwright.real-backend.config.ts"],
            ROOT / "frontend",
            ["results.json", "playwright-report/index.html"],
        ),
    }
    environment = {"python": sys.version.split()[0], "execution": "local test commands"}
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    environment["git_sha"] = sha.stdout.strip() or None
    checks = []
    for name in args.checks:
        print(f"Running {name}; report: {directory}", flush=True)
        command, cwd, required = commands[name]
        checks.append(
            run_check(
                name,
                command,
                cwd=cwd,
                output=directory / name,
                required=required,
                timeout=args.timeout,
            )
        )
        write_summary(directory, checks, environment=environment)
    print(f"Report: {directory / 'index.html'}", flush=True)
    return (
        2
        if any(item["status"] == "error" for item in checks)
        else int(any(item["status"] != "passed" for item in checks))
    )


if __name__ == "__main__":
    raise SystemExit(main())
