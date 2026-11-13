"""CPU-only recovery regressions; never starts a reconstruction process."""

import concurrent.futures
import contextlib
import importlib.util
import io
import json
import os
import shlex
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reconstruction_runner", ROOT / "backend/app/gateway/reconstructions/runner.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def load_ssh():
    package = types.ModuleType("recovery_test_package")
    package.__path__ = []
    config = types.ModuleType("recovery_test_package.config")
    config.TERMINAL = {"completed", "failed", "cancelled"}
    config.ReconstructionConfig = object
    spec = importlib.util.spec_from_file_location(
        "recovery_test_package.ssh", ROOT / "backend/app/gateway/reconstructions/ssh.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {"recovery_test_package": package, "recovery_test_package.config": config},
    ):
        spec.loader.exec_module(module)
    return module


ssh = load_ssh()


class ReconstructionRecovery(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "job"
        self.root.mkdir()
        self.proc = self.base / "proc"
        (self.proc / "sys/kernel/random").mkdir(parents=True)
        (self.proc / "sys/kernel/random/boot_id").write_text("boot-one")
        self.now = 10000
        os.utime(self.root, (self.now, self.now))

    def process(self, pid, ticks, *, state="S", arguments=None):
        directory = self.proc / str(pid)
        directory.mkdir(exist_ok=True)
        # comm may itself contain spaces and parentheses.
        fields = [state] + ["0"] * 18 + [str(ticks)] + ["0"] * 10
        (directory / "stat").write_text(
            str(pid) + " (python worker (job)) " + " ".join(fields)
        )
        (directory / "cmdline").write_bytes(
            b"\0".join(
                str(a).encode() for a in (arguments or ["worker", str(self.root)])
            )
        )
        return {"pid": pid, "start_ticks": str(ticks), "boot_id": "boot-one"}

    def state(self, *, supervisor=None, child=None, heartbeat=None):
        (self.root / ".started").mkdir(exist_ok=True)
        value = {
            "schema_version": 1,
            "supervisor": supervisor,
            "child": child,
            "heartbeat_at": self.now if heartbeat is None else heartbeat,
        }
        (self.root / ".started/supervisor.json").write_text(json.dumps(value))
        (self.root / "status.json").write_text(
            json.dumps(
                {
                    "status": "running",
                    "stage": "preprocessing",
                    "pipeline_profile": "flux3_rgb_subject_v1",
                    "preprocess_progress": {"completed": 3, "total": 10},
                }
            )
        )
        return value

    def inspect(self):
        return runner.inspect_job(self.root, now=self.now, proc_root=self.proc)

    def test_stale_claim_without_status_is_interrupted(self):
        marker = self.root / ".started"
        marker.mkdir()
        os.utime(marker, (1, 1))
        os.utime(self.root, (1, 1))
        value = self.inspect()
        self.assertEqual(
            (value["status"], value["error_code"]), ("failed", "interrupted")
        )
        self.assertTrue(marker.is_dir())
        self.assertFalse(
            (self.root / "status.json").exists(), "inspection is read-only"
        )

    def test_supervisor_loss_detected_even_with_live_orphan_child(self):
        self.state(
            supervisor={"pid": 410, "start_ticks": "4", "boot_id": "boot-one"},
            child=self.process(420, 9),
        )
        value = self.inspect()
        self.assertEqual(
            (value["status"], value["error_code"]), ("failed", "interrupted")
        )
        self.assertTrue(value["child_alive"])
        self.assertTrue(value["related_process_alive"])

    def test_surviving_flux_grandchild_is_reported_for_manual_review(self):
        self.state(
            supervisor={"pid": 410, "start_ticks": "4", "boot_id": "boot-one"},
            child={"pid": 420, "start_ticks": "9", "boot_id": "boot-one"},
        )
        self.process(
            430, 10, arguments=["brush_app", str(self.root) + "/projects/flux3/dataset"]
        )
        value = self.inspect()
        self.assertEqual(value["error_code"], "interrupted")
        self.assertFalse(value["child_alive"])
        self.assertTrue(value["related_process_alive"])

    def test_live_processes_keep_flux_frame_progress(self):
        self.state(supervisor=self.process(410, 4), child=self.process(420, 9))
        value = self.inspect()
        self.assertEqual(value["status"], "running")
        self.assertEqual(value["stage"], "preprocessing")
        self.assertEqual(value["preprocess_progress"], {"completed": 3, "total": 10})

    def test_reused_pid_does_not_count_as_live_supervisor(self):
        supervisor = self.process(410, 4)
        self.process(410, 99)
        self.state(supervisor=supervisor, child=self.process(420, 9))
        self.assertEqual(self.inspect()["error_code"], "interrupted")

    def test_reboot_invalidates_same_pid_and_ticks(self):
        self.state(supervisor=self.process(410, 4), child=self.process(420, 9))
        (self.proc / "sys/kernel/random/boot_id").write_text("boot-two")
        self.assertEqual(self.inspect()["status"], "failed")

    def test_zombie_is_not_a_live_supervisor(self):
        self.state(supervisor=self.process(410, 4, state="Z"))
        self.assertEqual(self.inspect()["status"], "failed")

    def test_child_exit_gets_terminal_write_grace_then_fails(self):
        self.state(
            supervisor=self.process(410, 4),
            child={"pid": 420, "start_ticks": "9", "boot_id": "boot-one"},
        )
        self.assertEqual(self.inspect()["status"], "running")
        self.now += 121
        value = self.inspect()
        self.assertEqual(value["error_code"], "interrupted")

    def test_live_supervisor_can_validate_large_artifact_after_child_exit(self):
        state = self.state(
            supervisor=self.process(410, 4),
            child={"pid": 420, "start_ticks": "9", "boot_id": "boot-one"},
            heartbeat=1,
        )
        state["phase"] = "validating"
        (self.root / ".started/supervisor.json").write_text(json.dumps(state))
        self.assertEqual(self.inspect()["status"], "running")

    def test_terminal_artifact_survives_dead_processes(self):
        self.state(supervisor={"pid": 410, "start_ticks": "4", "boot_id": "boot-one"})
        expected = {
            "status": "completed",
            "stage": "completed",
            "artifact": {"relative_path": "projects/a/final.ply"},
        }
        (self.root / "status.json").write_text(json.dumps(expected))
        self.assertEqual(self.inspect(), expected)

    def test_completion_committed_during_liveness_probe_beats_interruption(self):
        self.state(supervisor={"pid": 410, "start_ticks": "4", "boot_id": "boot-one"})
        expected = {
            "status": "completed",
            "stage": "completed",
            "artifact": {"kind": "point_cloud"},
        }

        def exited(*args):
            (self.root / "status.json").write_text(json.dumps(expected))
            return False

        with patch.object(runner, "process_alive", side_effect=exited):
            self.assertEqual(self.inspect(), expected)

    def test_old_pid_without_fingerprint_requires_job_scoped_cmdline(self):
        (self.root / ".started").mkdir()
        self.process(420, 9)
        (self.root / "status.json").write_text(
            json.dumps({"status": "running", "stage": "training", "pid": 420})
        )
        os.utime(self.root / "status.json", (1, 1))
        os.utime(self.root / ".started", (1, 1))
        os.utime(self.root, (1, 1))
        self.assertEqual(self.inspect()["status"], "running")
        self.process(420, 100, arguments=["unrelated-worker"])
        self.assertEqual(self.inspect()["status"], "failed")

    def test_unstarted_upload_has_bounded_grace(self):
        self.assertEqual(self.inspect()["status"], "transferring")
        os.utime(self.root, (1, 1))
        value = self.inspect()
        self.assertEqual(
            (value["status"], value["error_code"]), ("failed", "not_started")
        )

    def test_missing_remote_directory_is_explicit(self):
        self.root.rmdir()
        self.assertTrue(self.inspect()["remote_missing"])

    def test_persistent_claim_never_starts_second_process(self):
        (self.root / ".started").mkdir()
        with patch.object(runner.subprocess, "Popen") as launch:
            runner.run(self.root)
        launch.assert_not_called()

    def test_concurrent_atomic_writes_do_not_share_temporary_path(self):
        destination = self.root / "supervisor.json"

        def write(index):
            for turn in range(15):
                runner.write_json(
                    destination, {"writer": index, "turn": turn, "text": "x" * 1000}
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(8)))
        self.assertIn(json.loads(destination.read_text())["writer"], range(8))
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_supervisor_keeps_heartbeat_separate_from_flux_progress(self):
        config = {
            "executable": "unused",
            "quality": "balanced",
            "input": ".",
            "preprocessing": "flux3",
            "flux3": {"python": "fake-python"},
        }
        (self.root / "config.json").write_text(json.dumps(config))
        fake_process = Mock(pid=420)
        fake_process.poll.side_effect = [None, 0]
        fake_process.wait.return_value = 0
        progress = {
            "status": "running",
            "stage": "preprocessing",
            "pipeline_profile": "flux3_rgb_subject_v1",
            "preprocess_progress": {"completed": 3, "total": 10},
        }

        def spawn(*args, **kwargs):
            runner.write_json(self.root / "status.json", progress)
            return fake_process

        def waiting(_):
            self.assertEqual(runner.read_json(self.root / "status.json"), progress)
            lifecycle = runner.read_json(self.root / ".started/supervisor.json")
            self.assertEqual(lifecycle["child"]["pid"], 420)
            self.assertGreater(lifecycle["heartbeat_at"], 0)

        def identity(pid):
            return {"pid": pid, "start_ticks": "4", "boot_id": "boot-one"}

        with (
            patch.object(runner.subprocess, "Popen", side_effect=spawn) as launch,
            patch.object(runner, "process_identity", side_effect=identity),
            patch.object(runner.time, "sleep", side_effect=waiting),
            patch.object(
                runner, "validate_result", return_value={"kind": "point_cloud"}
            ),
        ):
            runner.run(self.root)
            runner.run(self.root)
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(
            runner.read_json(self.root / "status.json")["status"], "completed"
        )

    def test_inspection_protocol_supports_existing_job_without_runner_upgrade(self):
        (self.root / "status.json").write_text(
            json.dumps({"status": "completed", "artifact": {"kind": "point_cloud"}})
        )
        remote = ssh.SSHRemote(object())
        remote.root = lambda _: str(self.root)
        client, sftp = Mock(), Mock()
        sftp.listdir.side_effect = FileNotFoundError
        sftp.open.side_effect = FileNotFoundError

        def execute(command, **kwargs):
            self.assertFalse((self.root / "runner.py").exists())
            arguments = shlex.split(command)
            self.assertEqual(arguments[:2], ["python3", "-c"])
            output = io.StringIO()
            with (
                patch.object(sys, "argv", ["-c", arguments[3]]),
                contextlib.redirect_stdout(output),
            ):
                exec(arguments[2], {})
            stream = io.BytesIO(output.getvalue().encode("utf-8"))
            stream.channel = types.SimpleNamespace(recv_exit_status=lambda: 0)
            return None, stream, io.BytesIO()

        client.exec_command.side_effect = execute

        @contextlib.contextmanager
        def connection():
            yield client, sftp

        remote.connection = connection
        value = remote.inspect("unused")
        self.assertEqual(value["status"], "completed")
        self.assertEqual(value["artifact"]["kind"], "point_cloud")
        self.assertEqual(value["log"], "")

    def test_ssh_submit_does_not_even_launch_noop_supervisor_for_existing_claim(self):
        remote = ssh.SSHRemote(object())
        remote.root = lambda _: str(self.root)
        remote.exists = Mock(return_value=True)
        remote.mkdir = Mock()
        remote.inspect = Mock(
            return_value={"status": "failed", "error_code": "interrupted"}
        )
        client, sftp = Mock(), Mock()

        @contextlib.contextmanager
        def connection():
            yield client, sftp

        remote.connection = connection
        result = remote.submit({"id": "existing"}, self.root)
        client.exec_command.assert_not_called()
        sftp.put.assert_not_called()
        self.assertEqual(result["error_code"], "interrupted")


if __name__ == "__main__":
    unittest.main()
