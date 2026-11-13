"""Standalone remote supervisor, copied over SFTP. Python 3.8+, standard library only."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TERMINAL = {"completed", "failed", "cancelled"}
RECOVERY_GRACE_SECONDS = 120


def write_json(path, value):
    # A heartbeat and a terminal update must never share a temporary filename.
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".part", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(20):
            try:
                os.replace(name, path)
                break
            except PermissionError:
                # Windows can briefly deny replacing a concurrently replaced file.
                if os.name != "nt" or attempt == 19:
                    raise
                time.sleep(0.005)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def process_identity(pid, proc_root=Path("/proc")):
    """Linux PID identity survives neither PID recycling nor a machine reboot."""
    try:
        pid = int(pid)
        if pid <= 0:
            return {}
        text = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
        # The command name between parentheses may contain spaces or ')'.
        fields = text[text.rfind(")") + 2 :].split()
        if fields[0] in {"Z", "X", "x"}:
            return {}
        return {"pid": pid, "start_ticks": fields[19], "boot_id": (proc_root / "sys/kernel/random/boot_id").read_text(encoding="ascii").strip()}
    except (OSError, ValueError, IndexError, TypeError):
        return {}


def process_alive(identity, proc_root=Path("/proc")):
    if not isinstance(identity, dict) or not all(identity.get(key) for key in ("pid", "start_ticks", "boot_id")):
        return False
    return process_identity(identity["pid"], proc_root) == identity


def scoped_processes(root, proc_root):
    """Conservative compatibility for old runners that recorded only a child PID."""
    try:
        entries = proc_root.iterdir()
        for entry in entries:
            if not entry.name.isdigit() or int(entry.name) == os.getpid():
                continue
            try:
                args = (entry / "cmdline").read_bytes().decode("utf-8", errors="replace").split("\0")
                if any(arg == str(root) or arg.startswith(str(root) + "/") for arg in args) and process_identity(entry.name, proc_root):
                    return True
            except OSError:
                continue
    except OSError:
        pass
    return False


def latest_activity(root, include_uploads=False):
    paths = [root, root / ".started", root / "status.json", root / "runner.log"]
    if include_uploads:
        try:
            paths.extend((root / "source").iterdir())
        except OSError:
            pass
    timestamps = []
    for path in paths:
        try:
            timestamps.append(path.stat().st_mtime)
        except OSError:
            pass
    return max(timestamps) if timestamps else None


def inspect_job(root, now=None, proc_root=Path("/proc")):
    """Read-only protocol: observes liveness; never removes a claim or starts work."""
    root, proc_root = Path(root).resolve(), Path(proc_root)
    now = time.time() if now is None else now
    result = read_json(root / "status.json")
    if result.get("status") in TERMINAL:
        return result
    claimed = (root / ".started").exists()
    if not claimed:
        activity = latest_activity(root, include_uploads=True)
        value = {**result, "status": "transferring", "stage": "transferring", "remote_started": False, "remote_missing": not root.exists()}
        if activity is not None and now - activity > RECOVERY_GRACE_SECONDS:
            value.update(status="failed", stage="failed", error_code="not_started", error="素材传输或远程启动已中断；请新建任务重试")
        return value

    lifecycle = read_json(root / ".started" / "supervisor.json")
    supervisor = lifecycle.get("supervisor")
    if supervisor:
        supervisor_alive = process_alive(supervisor, proc_root)
        child_alive = process_alive(lifecycle.get("child"), proc_root)
        value = {"status": "running", "stage": "starting", **result, "remote_started": True, "supervisor_alive": supervisor_alive, "child_alive": child_alive, "heartbeat_at": lifecycle.get("heartbeat_at")}
        heartbeat = lifecycle.get("heartbeat_at")
        recent = isinstance(heartbeat, (int, float)) and now - heartbeat <= RECOVERY_GRACE_SECONDS
        # A just-exited child gives the live supervisor time to validate its output
        # and atomically publish a terminal status. Never mistake that race for loss.
        validating = lifecycle.get("phase") == "validating"
        if not supervisor_alive or (not child_alive and not recent and not validating):
            # The supervisor may have committed completion between our first
            # status read and the /proc snapshot, then exited normally.
            latest = read_json(root / "status.json")
            if latest.get("status") in TERMINAL:
                return latest
            related = child_alive or scoped_processes(root, proc_root)
            message = "远程监督进程或训练进程已中断；已保留素材、日志和防重标记"
            if related:
                message += "；仍发现关联子进程，请管理员核对后再新建任务，系统不会自动重启"
            else:
                message += "；请新建任务重试"
            value.update(status="failed", stage="failed", error_code="interrupted", related_process_alive=related, error=message)
        return value

    activity = latest_activity(root)
    if scoped_processes(root, proc_root) or (activity is not None and now - activity <= RECOVERY_GRACE_SECONDS):
        return {"status": "running", "stage": "starting", **result, "remote_started": True, "legacy_runner": True}
    latest = read_json(root / "status.json")
    if latest.get("status") in TERMINAL:
        return latest
    return {**result, "status": "failed", "stage": "failed", "remote_started": True, "legacy_runner": True, "error_code": "interrupted", "error": "远程启动标记已遗留且未发现关联进程；防重标记已保留，请新建任务重试"}


def validate_result(root):
    # Keep this lazy: the read-only inspector for old jobs is executed from
    # memory and must not require a helper absent from that job's directory.
    if __package__:
        from .ply_validation import inspect_ply
    else:
        from ply_validation import inspect_ply

    fused = read_json(root / "pipeline_result.json")
    if fused:
        if fused.get("schema_version") != 1 or fused.get("pipeline_profile") not in {"flux3_rgb_subject_v1", "flux_ooosplat_parallel_v2"} or fused.get("status") != "completed":
            raise ValueError("FLUX3 融合重建尚未完成")
        path = Path(fused["output"]["finalPly"]).resolve()
    else:
        projects = list((root / "projects").glob("*/project.json"))
        if len(projects) != 1:
            raise ValueError("未找到唯一的重建项目记录")
        project = read_json(projects[0])
        if project.get("status") != "completed":
            raise ValueError("OOOSplat 未报告重建完成")
        output = project.get("output") or {}
        path = Path(output.get("finalPly") or projects[0].parent / "final.ply").resolve()
    path.relative_to((root / "projects").resolve())
    size = path.stat().st_size
    if size <= 0 or size > 8 * 1024**3:
        raise ValueError("结果文件大小无效或超过 8 GiB")
    info = inspect_ply(path, size, include_digest=True)
    info.pop("format")
    result = {"relative_path": str(path.relative_to(root.resolve())), "size": size, **info}
    if fused.get("artifacts", {}).get("rgb"):
        rgb = Path(fused["artifacts"]["rgb"]["path"]).resolve()
        rgb.relative_to((root / "projects").resolve())
        size = rgb.stat().st_size
        extra = inspect_ply(rgb, size, include_digest=True)
        extra.pop("format")
        expected = fused["artifacts"]["rgb"].get("sha256")
        if expected and expected != extra["sha256"]:
            raise ValueError("RGB产物摘要不符")
        result["variants"] = {"rgb": {"relative_path": str(rgb.relative_to(root.resolve())), "size": size, **extra}}
    return result


def run(root, resume=False):
    root = Path(root).resolve()
    try:
        (root / ".started").mkdir()
    except FileExistsError:
        if not resume:
            return
    lock = (root / ".started/supervisor.lock").open("a+")
    try:
        if os.name == "posix":
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = read_json(root / ".started/supervisor.json")
        if resume:
            if process_alive(previous.get("supervisor")) or process_alive(previous.get("child")):
                raise RuntimeError("原监督器或子进程仍存活，拒绝重复续跑")
            if not read_json(root / "config.json").get("parallel"):
                raise ValueError("仅并发任务支持此续跑入口")
            if read_json(root / "status.json").get("status") == "completed":
                raise ValueError("任务已完成")
            if (root / "cancel.request").exists():
                (root / "cancel.request").rename(root / ("cancel-previous-" + str(time.time_ns()) + ".request"))
        return _run_supervised(root, resume)
    finally:
        lock.close()


def _run_supervised(root, resume=False):
    status = root / "status.json"
    lifecycle_path = root / ".started" / "supervisor.json"
    lifecycle = {"schema_version": 1, "supervisor": process_identity(os.getpid()), "child": None, "phase": "starting", "heartbeat_at": time.time()}
    write_json(lifecycle_path, lifecycle)
    if (root / "cancel.request").exists():
        write_json(status, {"status": "cancelled", "stage": "cancelled"})
        return
    config = read_json(root / "config.json")
    try:
        arguments = [config["executable"], "generate", "--projects-root", str(root / "projects"), "--quality", config["quality"], str(root / "source" / config["input"])]
        fused = config.get("preprocessing") == "flux3"
        parallel = config.get("parallel")
        if parallel:
            arguments = [parallel["python"], str(Path(parallel["root"]) / "scripts/flux_ooosplat_gateway.py"), str(root)]
            if resume:
                arguments.append("--resume")
        elif fused:
            arguments = [config["flux3"]["python"], str(root / "flux_pipeline.py"), str(root)]
        with (root / "runner.log").open("ab", buffering=0) as log:
            initial = {"status": "running", "stage": "starting"}
            if fused or parallel:
                initial["pipeline_profile"] = "flux_ooosplat_parallel_v2" if parallel else "flux3_rgb_subject_v1"
            write_json(status, initial)
            process = subprocess.Popen(arguments, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            lifecycle.update(child=process_identity(process.pid), phase="running", heartbeat_at=time.time())
            write_json(lifecycle_path, lifecycle)
            cancelled = False
            while process.poll() is None:
                lifecycle["heartbeat_at"] = time.time()
                # FLUX owns its per-image status.json progress while it runs.
                write_json(lifecycle_path, lifecycle)
                if (root / "cancel.request").exists():
                    cancelled = True
                    if fused or parallel:
                        # Adapter cancels only its own subprocess / queued prompt.
                        # An active FLUX image finishes before cancellation is acknowledged.
                        time.sleep(1)
                        continue
                    # Only the process group created for this exact job is signalled.
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    break
                time.sleep(1)
            code = process.wait()
        if cancelled or ((fused or parallel) and code == 130):
            write_json(status, {"status": "cancelled", "stage": "cancelled"})
        elif code != 0:
            details = read_json(root / "projects/parallel/batch/status.json") if parallel else {}
            write_json(status, {"status": "failed", "stage": "failed", "error": details.get("error") or "OOOSplat 运行失败，退出码 " + str(code)})
        else:
            # Large PLY validation may take longer than the liveness grace.
            # The supervisor identity remains authoritative in this explicit phase.
            lifecycle.update(phase="validating", heartbeat_at=time.time())
            write_json(lifecycle_path, lifecycle)
            artifact = validate_result(root)
            write_json(status, {"status": "completed", "stage": "completed", "artifact": artifact})
    except Exception as error:
        write_json(status, {"status": "failed", "stage": "failed", "error": str(error)[:500]})


if __name__ == "__main__":
    if sys.argv[1] == "--inspect":
        print(json.dumps(inspect_job(sys.argv[2]), ensure_ascii=False))
    elif sys.argv[1] == "--resume":
        run(sys.argv[2], resume=True)
    else:
        run(sys.argv[1])
