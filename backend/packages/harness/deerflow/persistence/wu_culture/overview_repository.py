"""Published discovery and admin-only, evidence-bound graph review metadata."""

import asyncio
import base64
import hashlib
import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import load_only
from wu_culture.authorization import evaluate_source_access
from wu_culture.models import AuthorizationStatus, AuthorizedUse, VisibilityScope

from .graph_repository import _graph_release_expression
from .model import EvidenceRow, KnowledgeReleaseItemRow, KnowledgeReleaseRow, KnowledgeReleaseStateRow, SourceDocumentRow, TextChunkRow, WuEntityEvidenceRow, WuEntityRow, WuRelationEvidenceRow, WuRelationRow
from .repository import SqlSourceDocumentRepository


class OverviewConflict(ValueError):
    pass


def _record(row, evidence_ids):
    names = (
        ("id", "canonical_name", "entity_type", "dynasty", "extant_status", "summary", "review_status", "release_id")
        if isinstance(row, WuEntityRow)
        else ("id", "subject_id", "object_id", "relation_type", "start_time", "end_time", "confidence", "is_inferred", "review_status", "release_id")
    )
    return {**{key: getattr(row, key) for key in names}, "evidence_ids": sorted(evidence_ids)}


class SqlGraphOverviewRepository:
    def __init__(self, factory):
        self.factory = factory

    async def read(self, *, admin=False, directory=False, view="published", **options):
        working = view == "working"
        if working and not admin:
            raise PermissionError("Working graph requires administrator privileges")
        if working and options.get("release_id"):
            raise ValueError("工作图谱不绑定发布版本，请清除版本筛选。")
        async with self.factory() as session:
            state = await session.get(KnowledgeReleaseStateRow, "active")
            release = await session.get(KnowledgeReleaseRow, state.active_release_id) if state and state.active_release_id else None
            if not working and (release is None or release.status != "active" or (not admin and release.scope != "public")):
                return _page(release.id if release else None, [], [], [], directory=directory, admin=admin, **options)
            if not working and options.get("release_id") and options["release_id"] != release.id:
                raise OverviewConflict("知识版本已切换，请重新加载总览。")
            # Evidence must belong to the exact manifest, not merely to a source
            # that happens to occur in this Release. Authorization is rechecked
            # on every page, including component and directory reads.
            # Graph discovery needs only the linked Evidence locators. Loading
            # the entire Release (including quotations) makes small graphs scan
            # the full text corpus before either overview or directory can open.
            linked_evidence = select(WuEntityEvidenceRow.evidence_id).union(select(WuRelationEvidenceRow.evidence_id))
            statement = (
                select(EvidenceRow, SourceDocumentRow, TextChunkRow)
                .join(SourceDocumentRow, SourceDocumentRow.id == EvidenceRow.document_id)
                .join(TextChunkRow, (TextChunkRow.id == EvidenceRow.chunk_id) & (TextChunkRow.document_id == EvidenceRow.document_id))
                .where(EvidenceRow.id.in_(linked_evidence))
                .options(
                    load_only(EvidenceRow.id, EvidenceRow.document_id, EvidenceRow.chunk_id, EvidenceRow.source_level, EvidenceRow.review_status, raiseload=True),
                    load_only(TextChunkRow.id, TextChunkRow.page_start, TextChunkRow.page_end, TextChunkRow.volume, TextChunkRow.review_status, raiseload=True),
                )
                .order_by(EvidenceRow.id)
            )
            if not working:
                statement = statement.join(KnowledgeReleaseItemRow, (KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id) & (KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id)).where(
                    KnowledgeReleaseItemRow.release_id == release.id
                )
            records = (await session.execute(statement)).all()
            allowed = {}
            use = AuthorizedUse.INTERNAL_PROCESSING if working or (admin and release.scope == "internal") else AuthorizedUse.PUBLIC_QUOTE
            source_access = {}
            authorization_pending = set()
            for evidence, document, chunk in records:
                if not admin and (evidence.review_status != "reviewed" or chunk.review_status != "reviewed"):
                    continue
                if document.id not in source_access:
                    source = SqlSourceDocumentRepository._row_to_document(document)
                    source_access[document.id] = evaluate_source_access(source, use=use).allowed
                    # Source managers may inspect already-persisted review
                    # metadata for new unconfirmed internal sources. This is
                    # not permission to process text, index, quote or publish.
                    if (
                        working
                        and source.authorization_status == AuthorizationStatus.UNCONFIRMED
                        and source.visibility_scope == VisibilityScope.INTERNAL
                        and not source.authorized_uses
                        and source.authorization_valid_from is None
                        and source.authorization_valid_until is None
                    ):
                        source_access[document.id] = True
                        authorization_pending.add(document.id)
                if not source_access[document.id]:
                    continue
                allowed[evidence.id] = {
                    "evidence_id": evidence.id,
                    "document_id": document.id,
                    "document_title": document.title,
                    "chunk_id": chunk.id,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "volume": chunk.volume,
                    "source_level": evidence.source_level,
                    "review_status": evidence.review_status,
                }
            entity_evidence = defaultdict(set)
            relation_evidence = defaultdict(set)
            # Join the manifest before loading linkage rows; never scan links
            # belonging only to other knowledge editions or build giant INs.
            entity_links = select(WuEntityEvidenceRow.entity_id, WuEntityEvidenceRow.evidence_id).join(EvidenceRow, EvidenceRow.id == WuEntityEvidenceRow.evidence_id)
            relation_links = select(WuRelationEvidenceRow.relation_id, WuRelationEvidenceRow.evidence_id).join(EvidenceRow, EvidenceRow.id == WuRelationEvidenceRow.evidence_id)
            if not working:
                manifest_join = (KnowledgeReleaseItemRow.chunk_id == EvidenceRow.chunk_id) & (KnowledgeReleaseItemRow.document_id == EvidenceRow.document_id)
                entity_links = entity_links.join(KnowledgeReleaseItemRow, manifest_join).where(KnowledgeReleaseItemRow.release_id == release.id)
                relation_links = relation_links.join(KnowledgeReleaseItemRow, manifest_join).where(KnowledgeReleaseItemRow.release_id == release.id)
            for entity_id, evidence_id in (await session.execute(entity_links)).all():
                if evidence_id in allowed:
                    entity_evidence[entity_id].add(evidence_id)
            for relation_id, evidence_id in (await session.execute(relation_links)).all():
                if evidence_id in allowed:
                    relation_evidence[relation_id].add(evidence_id)
            entities_query = select(WuEntityRow).order_by(WuEntityRow.id)
            relations_query = select(WuRelationRow).order_by(WuRelationRow.id)
            if not working:
                entities_query = entities_query.where(_graph_release_expression(WuEntityRow.release_id, release.id))
                relations_query = relations_query.where(_graph_release_expression(WuRelationRow.release_id, release.id))
            if not admin:
                # Working rows created/revised after publication are not part of
                # the published edition. Historical assets are never rewritten.
                entities_query = entities_query.where(WuEntityRow.review_status == "reviewed", WuEntityRow.updated_at <= release.created_at)
                relations_query = relations_query.where(WuRelationRow.review_status == "reviewed", WuRelationRow.updated_at <= release.created_at)
            entities = [_record(row, entity_evidence[row.id]) for row in (await session.scalars(entities_query)).all() if entity_evidence[row.id]]
            ids = {row["id"] for row in entities}
            edges = [_record(row, relation_evidence[row.id]) for row in (await session.scalars(relations_query)).all() if relation_evidence[row.id] and row.subject_id in ids and row.object_id in ids]
            return await asyncio.to_thread(
                _page,
                None if working else release.id,
                entities,
                edges,
                list(allowed.values()),
                directory=directory,
                admin=admin,
                view=view,
                authorization_pending_sources=len(authorization_pending),
                **options,
            )


def _page(
    release,
    nodes,
    edges,
    evidence,
    *,
    directory=False,
    admin=False,
    view="published",
    authorization_pending_sources=0,
    scope="all",
    relation_type=None,
    review_status=None,
    component_id=None,
    center=None,
    name=None,
    entity_type=None,
    dynasty=None,
    cursor=None,
    max_nodes=200,
    max_edges=300,
    release_id=None,
):
    by_id = {n["id"]: n for n in nodes}
    edges = sorted(
        (
            e
            for e in edges
            if (not relation_type or e["relation_type"] == relation_type)
            and (not review_status or e["review_status"] == review_status)
            and (admin and review_status == "rejected" or e["review_status"] != "rejected")
            and (scope != "people" or by_id[e["subject_id"]]["entity_type"] == by_id[e["object_id"]]["entity_type"] == "person")
        ),
        key=lambda e: e["id"],
    )
    if review_status != "rejected":
        nodes = [n for n in nodes if n["review_status"] != "rejected"]
        permitted = {n["id"] for n in nodes}
        edges = [e for e in edges if e["subject_id"] in permitted and e["object_id"] in permitted]
    adjacency = defaultdict(set)
    for e in edges:
        adjacency[e["subject_id"]].add(e["object_id"])
        adjacency[e["object_id"]].add(e["subject_id"])
    visited, groups, membership = set(), [], {}
    for key in sorted(adjacency):
        if key in visited:
            continue
        queue = [key]
        visited.add(key)
        for current in queue:
            membership[current] = key
            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        groups.append({"id": key, "label": "、".join(by_id[k]["canonical_name"] for k in queue[:3]), "total_nodes": len(queue), "total_edges": sum(len(adjacency[k]) for k in queue) // 2})
    edge_counts = defaultdict(int)
    for e in edges:
        edge_counts[membership[e["subject_id"]]] += 1
    for group in groups:
        group["total_edges"] = edge_counts[group["id"]]
    if directory:
        nodes = [
            dict(n, has_relations=n["id"] in adjacency, component_id=membership.get(n["id"]))
            for n in nodes
            if (not name or name.casefold() in n["canonical_name"].casefold())
            and (not entity_type or n["entity_type"] == entity_type)
            and (not dynasty or n["dynasty"] == dynasty)
            and (not review_status or n["review_status"] == review_status or n["id"] in adjacency)
        ]
        nodes.sort(key=lambda n: n["id"])
    else:
        if component_id:
            edges = [e for e in edges if membership[e["subject_id"]] == component_id]
        if center:
            edges = [e for e in edges if center in (e["subject_id"], e["object_id"])]
        connected = {key for e in edges for key in (e["subject_id"], e["object_id"])}
        nodes = [n for n in nodes if n["id"] in connected]
    fingerprint = hashlib.sha256(
        json.dumps([release, view, authorization_pending_sources, admin, directory, scope, relation_type, review_status, component_id, center, name, entity_type, dynasty, nodes, edges, evidence], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    offset = 0
    if cursor:
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            offset = payload["offset"]
            if type(offset) is not int or offset < 0:
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise ValueError("分页游标无效。") from exc
        if payload.get("fingerprint") != fingerprint:
            raise OverviewConflict("图谱范围、授权或筛选已改变，请重新加载。")
    if directory:
        returned_nodes, returned_edges = nodes[offset : offset + max_nodes], []
        end, total = offset + len(returned_nodes), len(nodes)
    else:
        returned_edges, selected = [], set()
        for edge in edges[offset : offset + max_edges]:
            endpoints = {edge["subject_id"], edge["object_id"]}
            if len(selected | endpoints) > max_nodes:
                break
            selected |= endpoints
            returned_edges.append(edge)
        returned_nodes = [n for n in nodes if n["id"] in selected]
        end, total = offset + len(returned_edges), len(edges)
    ids = {key for row in returned_nodes + returned_edges for key in row["evidence_ids"]}
    next_cursor = base64.urlsafe_b64encode(json.dumps({"offset": end, "fingerprint": fingerprint}).encode()).decode() if end < total else None
    return {
        "view": view,
        "authorization_pending_sources": authorization_pending_sources,
        "release_id": release,
        "nodes": returned_nodes,
        "edges": returned_edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "returned_nodes": len(returned_nodes),
        "returned_edges": len(returned_edges),
        "truncated": end < total,
        "next_cursor": next_cursor,
        "components": groups,
        "evidence": [e for e in evidence if e["evidence_id"] in ids],
    }
