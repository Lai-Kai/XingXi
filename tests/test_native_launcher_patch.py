"""Check the host-launcher patch without opening ports or changing the host."""

import errno
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
from textwrap import dedent
from types import SimpleNamespace
import unittest


BASELINE = dedent("""\
    def preflight(ports=PORTS):
        for port in ports:
            try:
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", port))
                    listener.listen(1)
            except OSError as error:
                if error.errno in (errno.EPERM, errno.EACCES):
                    raise RuntimeError("port access denied") from error
                raise RuntimeError("port unavailable") from error
""")


class ProbeSocket:
    def __init__(self, *, occupied=False, denied=False):
        self.occupied = occupied
        self.denied = denied
        self.reuse_address = False
        self.addresses = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def setsockopt(self, level, option, value):
        if (level, option) == (socket.SOL_SOCKET, socket.SO_REUSEADDR):
            self.reuse_address = bool(value)

    def bind(self, address):
        if self.denied:
            raise PermissionError(errno.EPERM, "operation not permitted")
        if self.occupied or not self.reuse_address:
            raise OSError(errno.EADDRINUSE, "address already in use")
        self.addresses.append(address)

    def listen(self, _backlog):
        pass


@unittest.skipUnless(
    shutil.which("patch"), "requires patch to validate the distributed patch"
)
class NativeLauncherPatchTests(unittest.TestCase):
    def load_preflight(self, probe, *, patched=True):
        source = BASELINE
        if patched:
            patch = (
                Path(__file__).resolve().parents[1]
                / "docs/patches/native-launcher-reuseaddr.patch"
            )
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "launch.py"
                target.write_text(source)
                result = subprocess.run(
                    ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                source = target.read_text()
        namespace = {
            "socket": SimpleNamespace(
                socket=lambda: probe,
                SOL_SOCKET=socket.SOL_SOCKET,
                SO_REUSEADDR=socket.SO_REUSEADDR,
            ),
            "errno": errno,
            "PORTS": (8001, 3000, 12026),
        }
        exec(compile(source, "<native-preflight>", "exec"), namespace)
        return namespace["preflight"]

    def test_original_probe_reports_time_wait_as_busy(self):
        with self.assertRaisesRegex(RuntimeError, "port unavailable"):
            self.load_preflight(ProbeSocket(), patched=False)()

    def test_patch_allows_time_wait_reuse_on_all_service_ports(self):
        probe = ProbeSocket()
        self.load_preflight(probe)()
        self.assertEqual(
            probe.addresses, [("127.0.0.1", port) for port in (8001, 3000, 12026)]
        )

    def test_patch_still_rejects_an_active_listener(self):
        with self.assertRaisesRegex(RuntimeError, "port unavailable"):
            self.load_preflight(ProbeSocket(occupied=True))()

    def test_patch_still_reports_permission_denied(self):
        with self.assertRaisesRegex(RuntimeError, "port access denied"):
            self.load_preflight(ProbeSocket(denied=True))()


if __name__ == "__main__":
    unittest.main()
