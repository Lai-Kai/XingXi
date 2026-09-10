from __future__ import annotations

from enum import StrEnum


class BusinessRole(StrEnum):
    PUBLIC = "public"
    RESEARCHER = "researcher"
    CULTURAL_INSTITUTION = "cultural_institution"
    GOVERNMENT = "government"
    STUDY_TEAM = "study_team"


class BusinessCapability(StrEnum):
    KNOWLEDGE_READ = "knowledge:read"
    CHAT_USE = "chat:use"
    MAP_READ = "map:read"
    PROJECT_MANAGE = "project:manage"
    EVIDENCE_RESEARCH = "evidence:research"
    EXPORT_CREATE = "export:create"
    STUDY_ROUTE_USE = "study-route:use"
    SOURCE_MANAGE = "source:manage"
    SOURCE_REVIEW = "source:review"
    GOVERNANCE_READ = "governance:read"
    QUALITY_READ = "quality:read"
    QUALITY_REVIEW = "quality:review"
    QUALITY_ADMIN = "quality:admin"
    RELEASE_APPROVE = "release:approve"


_COMMON = frozenset(
    {
        BusinessCapability.KNOWLEDGE_READ,
        BusinessCapability.CHAT_USE,
        BusinessCapability.MAP_READ,
    }
)

_ROLE_CAPABILITIES: dict[BusinessRole, frozenset[BusinessCapability]] = {
    BusinessRole.PUBLIC: _COMMON,
    BusinessRole.RESEARCHER: _COMMON
    | {
        BusinessCapability.PROJECT_MANAGE,
        BusinessCapability.EVIDENCE_RESEARCH,
        BusinessCapability.EXPORT_CREATE,
    },
    BusinessRole.CULTURAL_INSTITUTION: _COMMON
    | {
        BusinessCapability.EVIDENCE_RESEARCH,
        BusinessCapability.SOURCE_MANAGE,
        BusinessCapability.SOURCE_REVIEW,
    },
    BusinessRole.GOVERNMENT: _COMMON
    | {
        BusinessCapability.EVIDENCE_RESEARCH,
        BusinessCapability.GOVERNANCE_READ,
        BusinessCapability.QUALITY_READ,
        BusinessCapability.QUALITY_REVIEW,
        BusinessCapability.RELEASE_APPROVE,
    },
    BusinessRole.STUDY_TEAM: _COMMON
    | {
        BusinessCapability.PROJECT_MANAGE,
        BusinessCapability.EXPORT_CREATE,
        BusinessCapability.STUDY_ROUTE_USE,
    },
}


def capabilities_for(
    system_role: str,
    business_role: BusinessRole | str,
) -> frozenset[BusinessCapability]:
    if system_role == "admin":
        return frozenset(BusinessCapability)
    return _ROLE_CAPABILITIES[BusinessRole(business_role)]
