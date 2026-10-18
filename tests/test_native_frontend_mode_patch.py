"""Exercise the distributed native frontend patch without ports or host writes."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("patch"), "requires patch")
class NativeFrontendModePatchTests(unittest.TestCase):
    def load_launcher(self, *, patched=True, build_fails=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        state = root / "runtime"
        (state / "logs").mkdir(parents=True)
        source = (REPO / "tests/fixtures/native_launcher_start.txt").read_text()
        if patched:
            target = root / "launch.py"
            target.write_text(source)
            result = subprocess.run(
                [
                    "patch",
                    "--batch",
                    "--fuzz=0",
                    "-p1",
                    "-i",
                    str(
                        REPO / "docs/patches/native-launcher-production-frontend.patch"
                    ),
                ],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source = target.read_text()

        calls = []

        def run(command, **kwargs):
            calls.append(("run", command, kwargs))
            if build_fails and "build" in command:
                raise subprocess.CalledProcessError(1, command)

        def spawn(command, **kwargs):
            calls.append(("spawn", command, kwargs))
            return SimpleNamespace(pid=123, poll=lambda: None, wait=Mock())

        namespace = {
            "ROOT": root,
            "STATE": state,
            "PYTHON": root / "python",
            "NODE": root / "node",
            "NEXT": root / "next",
            "records": Mock(return_value=[]),
            "alive": Mock(return_value=False),
            "check_dependencies": Mock(),
            "preflight": Mock(),
            "prepare": Mock(),
            "nginx_command": Mock(return_value=["nginx"]),
            "fingerprint": Mock(return_value="identity"),
            "wait_http": Mock(),
            "stop": Mock(),
            "json": json,
            "subprocess": SimpleNamespace(
                run=Mock(side_effect=run),
                Popen=Mock(side_effect=spawn),
                DEVNULL=subprocess.DEVNULL,
                STDOUT=subprocess.STDOUT,
                TimeoutExpired=subprocess.TimeoutExpired,
            ),
        }
        exec(compile(source, "<native-launcher-start>", "exec"), namespace)
        return namespace, calls

    def start(self, launcher, env):
        with redirect_stdout(io.StringIO()):
            launcher["start"]({}, env)

    def frontend(self, calls):
        return next(
            call
            for call in calls
            if call[0] == "spawn" and str(call[1][1]).endswith("/next")
        )

    def test_original_launcher_serves_development_and_never_builds(self):
        launcher, calls = self.load_launcher(patched=False)
        self.start(launcher, {})
        self.assertEqual(self.frontend(calls)[1][2:4], ["dev", "--webpack"])
        self.assertFalse(any("build" in call[1] for call in calls))

    def test_default_builds_before_any_service_and_serves_production(self):
        launcher, calls = self.load_launcher()
        env = {"EXISTING_SETTING": "keep", "NODE_ENV": "development"}
        self.start(launcher, env)
        build_index = next(i for i, call in enumerate(calls) if "build" in call[1])
        first_spawn = next(i for i, call in enumerate(calls) if call[0] == "spawn")
        self.assertLess(build_index, first_spawn)
        build = calls[build_index]
        frontend = self.frontend(calls)
        self.assertEqual(build[1][2:], ["build", "--webpack"])
        self.assertTrue(build[2]["check"])
        self.assertEqual(
            frontend[1][2:], ["start", "--hostname", "127.0.0.1", "--port", "3000"]
        )
        self.assertEqual(build[2]["env"], frontend[2]["env"])
        self.assertEqual(frontend[2]["env"]["NODE_ENV"], "production")
        self.assertEqual(frontend[2]["env"]["EXISTING_SETTING"], "keep")
        self.assertEqual(env["NODE_ENV"], "development")
        self.assertEqual(frontend[2]["env"]["NEXT_PUBLIC_BACKEND_BASE_URL"], "")
        self.assertEqual(frontend[2]["env"]["NEXT_PUBLIC_LANGGRAPH_BASE_URL"], "")
        self.assertEqual(len([call for call in calls if call[0] == "spawn"]), 3)

    def test_explicit_production_mode(self):
        launcher, calls = self.load_launcher()
        self.start(launcher, {"DEERFLOW_FRONTEND_MODE": "production"})
        self.assertEqual(self.frontend(calls)[1][2], "start")

    def test_development_remains_available_without_building(self):
        launcher, calls = self.load_launcher()
        self.start(launcher, {"DEERFLOW_FRONTEND_MODE": "development"})
        frontend = self.frontend(calls)
        self.assertEqual(frontend[1][2:4], ["dev", "--webpack"])
        self.assertEqual(frontend[2]["env"]["NODE_ENV"], "development")
        self.assertFalse(any("build" in call[1] for call in calls))

    def test_invalid_mode_fails_before_preflight_or_launch(self):
        launcher, calls = self.load_launcher()
        with self.assertRaisesRegex(RuntimeError, "DEERFLOW_FRONTEND_MODE"):
            self.start(launcher, {"DEERFLOW_FRONTEND_MODE": "typo"})
        launcher["preflight"].assert_not_called()
        self.assertEqual(calls, [])

    def test_failed_build_does_not_start_any_service(self):
        launcher, calls = self.load_launcher(build_fails=True)
        with self.assertRaises(subprocess.CalledProcessError):
            self.start(launcher, {})
        self.assertFalse(any(call[0] == "spawn" for call in calls))
        self.assertFalse((launcher["STATE"] / "pids.json").exists())


if __name__ == "__main__":
    unittest.main()
