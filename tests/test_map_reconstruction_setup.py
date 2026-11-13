from pathlib import Path
import importlib.util
import os

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "map_setup", ROOT / "scripts/configure_map_reconstruction.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_authorized_key_is_loopback_only_and_idempotent(tmp_path):
    target = tmp_path / "authorized_keys"
    original = "ssh-ed25519 AAAAexisting existing-user\n"
    target.write_text(original)
    setup.authorize_key(target, "ssh-ed25519 AAAAnew generated-comment")
    once = target.read_text()
    setup.authorize_key(target, "ssh-ed25519 AAAAnew generated-comment")
    assert target.read_text() == once
    assert once.startswith(original)
    assert 'from="127.0.0.1",restrict ssh-ed25519 AAAAnew' in once
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600


def test_environment_update_preserves_other_settings_and_replaces_duplicates(tmp_path):
    target = tmp_path / ".env"
    target.write_text(
        "# keep this\nEXISTING_SETTING=unchanged\nXINGXI_TEST=old\nexport XINGXI_TEST=older\n"
    )
    setup.update_env(
        target, {"XINGXI_TEST": "/new/path", "XINGXI_OTHER": "http://127.0.0.1:18188"}
    )
    once = target.read_text()
    assert "# keep this\nEXISTING_SETTING=unchanged\n" in once
    assert once.count("XINGXI_TEST=") == 1
    assert "XINGXI_TEST=/new/path" in once
    setup.update_env(
        target, {"XINGXI_TEST": "/new/path", "XINGXI_OTHER": "http://127.0.0.1:18188"}
    )
    assert target.read_text() == once
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600


def test_configuration_uses_service_identity_without_password(tmp_path):
    settings = setup.ssh_settings("service-owner", tmp_path / "private-key")
    assert settings == {
        "host": "127.0.0.1",
        "port": 22,
        "user": "service-owner",
        "key_filename": str(tmp_path / "private-key"),
    }
    assert "password" not in settings
