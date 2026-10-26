"""Load only the pure launcher helper; no host services or ports are touched."""

import ast
import os
from pathlib import Path
import tempfile
import unittest


class NativeGatewayTemp(unittest.TestCase):
    def helper(self):
        source = Path(
            os.environ.get(
                "XINGXI_NATIVE_LAUNCHER",
                str(Path(__file__).resolve().parents[1] / "host-deployment/launch.py"),
            )
        )
        if not source.is_file():
            self.skipTest("Set XINGXI_NATIVE_LAUNCHER to this host's native launch.py")
        parsed = ast.parse(source.read_text(encoding="utf-8"))
        helper = next(
            node
            for node in parsed.body
            if isinstance(node, ast.FunctionDef) and node.name == "get_gateway_env"
        )
        namespace = {"Path": Path, "os": os}
        exec(
            compile(ast.Module(body=[helper], type_ignores=[]), str(source), "exec"),
            namespace,
        )
        return namespace["get_gateway_env"]

    def test_gateway_gets_private_data_directory_without_mutating_other_children(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"
            data.mkdir()
            env = {"DEER_FLOW_HOME": str(data), "TMPDIR": "/tmp", "TEMP": "/tmp"}
            gateway = self.helper()(env)
            target = data / "gateway-upload-tmp"
            self.assertTrue(target.is_dir())
            for variable in ("TMPDIR", "TMP", "TEMP"):
                self.assertEqual(gateway[variable], str(target.resolve()))
            self.assertEqual(env["TMPDIR"], "/tmp")
            if os.name == "posix":
                self.assertEqual(target.stat().st_mode & 0o777, 0o700)

    def test_existing_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "gateway-upload-tmp"
            target.write_text("keep")
            with self.assertRaises((RuntimeError, FileExistsError)):
                self.helper()({"DEER_FLOW_HOME": temporary})
            self.assertEqual(target.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
