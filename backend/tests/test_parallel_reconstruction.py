import json
from dataclasses import replace

import pytest

from app.gateway.reconstructions import runner
from app.gateway.reconstructions.config import ReconstructionConfig
from app.gateway.reconstructions.service import ReconstructionService
from app.gateway.reconstructions.ssh import SSHRemote


def test_parallel_result_preserves_native_and_rgb_contract(tmp_path):
    path = tmp_path / "projects/parallel/batch/scene/final.ply"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n0 0 0 255 0 0\n")
    rgb = path.with_name("rgb_points.ply")
    rgb.write_bytes(path.read_bytes())
    (tmp_path / "pipeline_result.json").write_text(json.dumps({"schema_version": 1, "pipeline_profile": "flux_ooosplat_parallel_v2", "status": "completed", "output": {"finalPly": str(path)}, "artifacts": {"rgb": {"path": str(rgb)}}}))
    result = runner.validate_result(tmp_path)
    assert result["point_count"] == 1
    assert result["variants"]["rgb"]["point_count"] == 1


def test_parallel_runner_config_defaults_to_opt_in(monkeypatch):
    monkeypatch.delenv("XINGXI_PARALLEL_RUNNER_ROOT", raising=False)
    assert ReconstructionConfig().parallel_runner_root == ""
    monkeypatch.setenv("XINGXI_PARALLEL_RUNNER_ROOT", "/data/runner/version")
    assert ReconstructionConfig().parallel_runner_root == "/data/runner/version"


@pytest.mark.asyncio
async def test_explicit_resume_uses_persisted_remote_and_rejects_completed():
    class Store:
        job = {"id": "a", "status": "failed", "parallel": {"root": "/data/runner"}, "files": [], "preprocessing": "none"}

        async def get(self, _):
            return dict(self.job)

        async def begin_resume(self, _):
            self.job.update(status="running", stage="resuming", error=None)
            return dict(self.job)

        async def patch(self, _, update):
            self.job.update(update)
            return dict(self.job)

    class Remote:
        calls = 0

        def resume(self, _):
            self.calls += 1
            return {"status": "running", "stage": "preparing"}

    store, remote = Store(), Remote()
    service = ReconstructionService(ReconstructionConfig(), store, remote)
    assert (await service.resume("a"))["status"] == "running"
    assert remote.calls == 1
    store.job["status"] = "completed"
    with pytest.raises(Exception) as exc:
        await service.resume("a")
    assert exc.value.status_code == 409
    assert remote.calls == 1


def test_parallel_submission_command_does_not_accept_arbitrary_script(tmp_path):
    config = replace(ReconstructionConfig(), parallel_runner_root="/data/pinned/runner")
    remote = SSHRemote(config)
    command = remote.resume_command("00000000-0000-0000-0000-000000000001")
    assert "--resume" in command
    assert "/runner.py" in command
