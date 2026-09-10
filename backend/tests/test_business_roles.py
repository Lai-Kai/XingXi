import asyncio
import tempfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.gateway.auth.models import User, UserResponse
from app.gateway.auth.roles import BusinessCapability, BusinessRole, capabilities_for
from app.gateway.deps import require_business_capability


def test_business_roles_expose_distinct_capabilities() -> None:
    public = capabilities_for("user", BusinessRole.PUBLIC)
    researcher = capabilities_for("user", BusinessRole.RESEARCHER)
    institution = capabilities_for("user", BusinessRole.CULTURAL_INSTITUTION)
    government = capabilities_for("user", BusinessRole.GOVERNMENT)
    study_team = capabilities_for("user", BusinessRole.STUDY_TEAM)

    assert BusinessCapability.KNOWLEDGE_READ in public
    assert BusinessCapability.PROJECT_MANAGE not in public
    assert BusinessCapability.PROJECT_MANAGE in researcher
    assert BusinessCapability.STUDY_ROUTE_USE in study_team
    assert BusinessCapability.SOURCE_MANAGE in institution
    assert BusinessCapability.GOVERNANCE_READ in government
    assert BusinessCapability.QUALITY_READ in government
    assert BusinessCapability.QUALITY_REVIEW in government
    assert BusinessCapability.QUALITY_ADMIN not in government
    assert len({public, researcher, institution, government, study_team}) == 5


def test_system_admin_keeps_every_business_capability() -> None:
    capabilities = capabilities_for("admin", BusinessRole.PUBLIC)
    assert capabilities == frozenset(BusinessCapability)


def test_legacy_users_receive_safe_business_role_defaults() -> None:
    regular = User(email="reader@example.com")
    admin = User(email="admin@example.com", system_role="admin")

    assert regular.business_role is BusinessRole.PUBLIC
    assert admin.effective_business_role is BusinessRole.GOVERNMENT


def test_user_response_exposes_role_organization_and_capabilities() -> None:
    user = User(
        email="archive@example.com",
        business_role=BusinessRole.CULTURAL_INSTITUTION,
        organization_name="木渎文博机构",
    )

    response = UserResponse.from_user(user)

    assert response.business_role is BusinessRole.CULTURAL_INSTITUTION
    assert response.organization_name == "木渎文博机构"
    assert BusinessCapability.SOURCE_MANAGE in response.capabilities


def test_business_profile_survives_repository_round_trip() -> None:
    from app.gateway.auth.repositories.sqlite import SQLiteUserRepository
    from deerflow.persistence.engine import close_engine, get_session_factory, init_engine

    async def run() -> None:
        with tempfile.TemporaryDirectory(dir=".deer-flow") as tmpdir:
            await init_engine(
                "sqlite",
                url=f"sqlite+aiosqlite:///{tmpdir}/roles.db",
                sqlite_dir=tmpdir,
            )
            try:
                repo = SQLiteUserRepository(get_session_factory())
                user = User(
                    email="researcher@example.com",
                    business_role=BusinessRole.RESEARCHER,
                    organization_name="地方文史研究中心",
                )
                await repo.create_user(user)
                fetched = await repo.get_user_by_email(user.email)
                assert fetched is not None
                assert fetched.business_role is BusinessRole.RESEARCHER
                assert fetched.organization_name == "地方文史研究中心"
                fetched.business_role = BusinessRole.STUDY_TEAM
                await repo.update_user(fetched)
                listed = await repo.list_users()
                assert [item.business_role for item in listed] == [BusinessRole.STUDY_TEAM]
            finally:
                await close_engine()

    asyncio.run(run())


def test_backend_enforces_business_capabilities() -> None:
    def request_for(role: BusinessRole) -> Request:
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
        request.state.user = SimpleNamespace(
            id=f"user-{role.value}",
            system_role="user",
            business_role=role,
        )
        return request

    institution = asyncio.run(
        require_business_capability(
            request_for(BusinessRole.CULTURAL_INSTITUTION),
            "source:manage",
            detail="forbidden",
        )
    )
    assert institution.id == "user-cultural_institution"

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            require_business_capability(
                request_for(BusinessRole.PUBLIC),
                "source:manage",
                detail="forbidden",
            )
        )
    assert denied.value.status_code == 403
