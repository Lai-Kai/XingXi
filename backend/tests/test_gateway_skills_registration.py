"""Exercise skill routes on the real Gateway, without a running service."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest


def test_gateway_registers_skill_management_routes():
    from app.gateway.app import create_app

    paths = create_app().openapi()["paths"]

    assert "/api/skills" in paths
    assert "get" in paths["/api/skills"]
    assert "put" in paths["/api/skills/{skill_name}"]
    assert "post" in paths["/api/skills/install"]


@pytest.mark.asyncio
async def test_real_gateway_lists_files_and_persists_admin_toggle(monkeypatch, tmp_path):
    from app.gateway.app import create_app
    from app.gateway.auth.models import User
    from app.gateway.deps import get_config
    from deerflow.config.extensions_config import ExtensionsConfig
    from deerflow.config.paths import Paths
    from deerflow.skills.storage.user_scoped_skill_storage import UserScopedSkillStorage

    skills_router = importlib.import_module("app.gateway.routers.skills")
    root = tmp_path / "skills"
    public = root / "public" / "research"
    public.mkdir(parents=True)
    (public / "SKILL.md").write_text("---\nname: research\ndescription: 文史研究\n---\n研究说明\n", encoding="utf-8")
    # Namespace directories without SKILL.md do not break the list.
    (root / "public" / "empty").mkdir()
    extensions_path = tmp_path / "extensions_config.json"
    extensions_path.write_text('{"mcpServers": {}, "skills": {}}', encoding="utf-8")
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(extensions_path))
    monkeypatch.setattr("deerflow.config.paths.get_paths", lambda: Paths(base_dir=tmp_path))
    storage = UserScopedSkillStorage("test-user", host_path=str(root))
    monkeypatch.setattr(skills_router, "_get_user_skill_storage", lambda config: storage)
    monkeypatch.setattr(skills_router, "get_extensions_config", ExtensionsConfig.from_file)
    monkeypatch.setattr(skills_router, "reload_extensions_config", lambda: None)

    async def refresh(_user_id):
        return None

    monkeypatch.setattr(skills_router, "refresh_user_skills_system_prompt_cache_async", refresh)
    app = create_app()
    # Keep the real routes and exception handlers; isolate authentication and IO.
    app.user_middleware.clear()
    user = User(email="skills-test@example.com", password_hash="unused", system_role="user", id=uuid4())

    @app.middleware("http")
    async def authenticate(request, call_next):
        request.state.user = user
        return await call_next(request)

    app.dependency_overrides[get_config] = lambda: SimpleNamespace()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/skills")
        assert response.status_code == 200, response.text
        assert response.json()["skills"] == [{"name": "research", "description": "文史研究", "license": None, "category": "public", "enabled": True, "editable": False}]
        assert (await client.put("/api/skills/research", json={"enabled": False})).status_code == 403
        user.system_role = "admin"
        response = await client.put("/api/skills/research", json={"enabled": False})
        assert response.status_code == 200, response.text
        assert (await client.get("/api/skills")).json()["skills"][0]["enabled"] is False
        assert ExtensionsConfig.from_file().skills["research"].enabled is False


def test_restored_scanner_allows_research_and_blocks_dynamic_execution(tmp_path: Path):
    # Import inside the test so a missing scanner reports a failure, not a
    # collection error that hides the route-registration regression.
    scanner = importlib.import_module("deerflow.skills.security_static_scanner")
    (tmp_path / "SKILL.md").write_text("---\nname: research\ndescription: Read historical sources\n---\n# Research\n", encoding="utf-8")
    config = SimpleNamespace(skill_scan=SimpleNamespace(enabled=True))
    scanner.enforce_static_scan(tmp_path, skill_name="research", app_config=config)
    (tmp_path / "script.py").write_text('eval(input("code: "))\n', encoding="utf-8")
    with pytest.raises(scanner.StaticScanBlockedError) as error:
        scanner.enforce_static_scan(tmp_path, skill_name="research", app_config=config)
    assert any(finding["severity"] == "CRITICAL" for finding in error.value.findings)
