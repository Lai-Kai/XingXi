from __future__ import annotations

from wu_culture.relations.service import RelationQuery, RelationService


def run_person_relation_qa(
    relations: RelationService,
    *,
    person_id: str,
    person_name: str,
) -> dict:
    if not person_id.strip():
        raise ValueError("person_id cannot be empty")
    if not person_name.strip():
        raise ValueError("person_name cannot be empty")
    hops = relations.one_hop(RelationQuery(entity_id=person_id, direction="both", limit=20))
    if not hops:
        return {
            "status": "refused",
            "answer": "当前检索范围内暂无明确记载。",
            "relations": [],
        }
    lines = []
    payload = []
    for rel in hops:
        other = rel.object_id if rel.subject_id == person_id else rel.subject_id
        evidence_note = f"（证据：{', '.join(rel.evidence_ids)}）" if rel.evidence_ids else "（推断关系）"
        lines.append(f"{person_name} —{rel.relation_type.value}→ {other}{evidence_note}")
        payload.append(rel.model_dump(mode="json"))
    return {
        "status": "answered",
        "answer": f"根据关系库，{person_name} 的一跳关联如下：\n" + "\n".join(lines),
        "relations": payload,
    }
