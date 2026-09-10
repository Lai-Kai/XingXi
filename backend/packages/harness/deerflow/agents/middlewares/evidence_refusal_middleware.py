"""Force structured refusal when retrieval lacks usable historical evidence."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime
from wu_culture.evidence_pack import EvidencePack, EvidencePackItem, EvidencePackStatus
from wu_culture.refusal import (
    RefusalReason,
    evaluate_refusal,
    is_historical_nonexistence_claim,
)

logger = logging.getLogger(__name__)

_INLINE_REASONING_RE = re.compile(r"<think>\s*([\s\S]*?)\s*</think>", re.IGNORECASE)


def _message_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                pieces.append(part["text"])
            else:
                return None
        return "\n".join(pieces) if pieces else None
    return None


def _set_message_text(message: AIMessage, text: str) -> AIMessage:
    content = message.content
    if isinstance(content, str) or content is None:
        return message.model_copy(update={"content": text})
    if isinstance(content, list):
        replaced = False
        new_parts: list[Any] = []
        for part in content:
            if not replaced and isinstance(part, str):
                new_parts.append(text)
                replaced = True
            elif not replaced and isinstance(part, dict) and part.get("type") in {"text", "output_text"}:
                new_parts.append({**part, "text": text})
                replaced = True
            else:
                new_parts.append(part)
        if not replaced:
            new_parts.append({"type": "text", "text": text})
        return message.model_copy(update={"content": new_parts})
    return message.model_copy(update={"content": text})


def _inline_reasoning(content: Any) -> str | None:
    text = _message_text(content)
    if not text:
        return None
    parts = [match.strip() for match in _INLINE_REASONING_RE.findall(text) if match.strip()]
    return "\n\n".join(parts) if parts else None


def _visible_answer(content: Any) -> str:
    """Return the model answer without provider-specific inline reasoning."""
    text = _message_text(content) or ""
    return _INLINE_REASONING_RE.sub("", text).strip()


def _guard_unverified_supplement(text: str) -> str:
    """Prevent an ungrounded supplement from making an absolute history claim."""
    guarded = text
    replacements = (
        ("历史上不存在", "当前本地检索未见记载"),
        ("从未存在", "当前本地检索未见记载"),
        ("可以断定不存在", "当前本地检索不足以判断存在与否"),
        ("确定没有", "当前本地检索未见"),
        ("并无此", "当前本地检索未见此"),
    )
    for source, target in replacements:
        guarded = guarded.replace(source, target)
    return guarded


def _preserve_reasoning(message: AIMessage) -> AIMessage:
    inline_reasoning = _inline_reasoning(message.content)
    if not inline_reasoning:
        return message

    additional_kwargs = dict(message.additional_kwargs or {})
    existing_reasoning = additional_kwargs.get("reasoning_content")
    if isinstance(existing_reasoning, str) and existing_reasoning.strip():
        if inline_reasoning not in existing_reasoning:
            additional_kwargs["reasoning_content"] = f"{existing_reasoning}\n\n{inline_reasoning}"
    else:
        additional_kwargs["reasoning_content"] = inline_reasoning
    return message.model_copy(update={"additional_kwargs": additional_kwargs})


def _has_tool_calls(message: AIMessage) -> bool:
    if message.tool_calls or getattr(message, "invalid_tool_calls", None):
        return True
    additional_kwargs = message.additional_kwargs or {}
    return bool(additional_kwargs.get("tool_calls") or additional_kwargs.get("function_call"))


def _latest_user_query(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage) and not (message.additional_kwargs or {}).get("hide_from_ui"):
            text = _message_text(message.content)
            if text:
                return text.strip()
    return ""


def _merge_evidence_packs(packs: list[EvidencePack]) -> EvidencePack | None:
    if not packs:
        return None

    # A model may search a broad term and then a more specific term. Treat all
    # packs from the same turn as one retrieval context so a later empty search
    # cannot hide an earlier supported source.
    items: list[EvidencePackItem] = []
    seen_keys: set[tuple[str, str]] = set()
    duplicate_count = 0
    for pack in reversed(packs):
        for item in pack.items:
            key = (item.evidence_id, item.chunk_id)
            if key in seen_keys:
                duplicate_count += 1
                continue
            seen_keys.add(key)
            items.append(item.model_copy(update={"rank": len(items) + 1}))

    token_budget = max(pack.token_budget for pack in packs)
    if items:
        status = EvidencePackStatus.READY
        used_tokens = min(sum(pack.used_tokens for pack in packs), token_budget)
    elif any(pack.status is EvidencePackStatus.INSUFFICIENT_BUDGET for pack in packs):
        status = EvidencePackStatus.INSUFFICIENT_BUDGET
        used_tokens = 0
    else:
        status = EvidencePackStatus.EMPTY
        used_tokens = 0
    return EvidencePack(
        release_id=next((pack.release_id for pack in reversed(packs) if pack.release_id), "unknown"),
        status=status,
        token_budget=token_budget,
        used_tokens=used_tokens,
        input_count=sum(pack.input_count for pack in packs),
        deduplicated_count=sum(pack.deduplicated_count for pack in packs) + duplicate_count,
        omitted_count=sum(pack.omitted_count for pack in packs),
        document_count=len({item.document_id for item in items}),
        items=tuple(items),
    )


def _latest_retrieval_context(messages: list[Any]) -> tuple[str | None, EvidencePack | None, list[str]]:
    statuses: list[str] = []
    packs: list[EvidencePack] = []
    document_ids: list[str] = []
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue
        text = _message_text(message.content)
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        # Graph/timeline tools also return a status, but they are not source
        # retrieval results and must not affect evidence refusal decisions.
        if "evidence_pack" not in data and "hits" not in data:
            continue
        if "status" in data:
            statuses.append(str(data.get("status") or "insufficient"))
            pack_data = data.get("evidence_pack")
            if isinstance(pack_data, dict):
                try:
                    packs.append(EvidencePack.model_validate(pack_data))
                except Exception:
                    logger.debug("Invalid evidence_pack in refusal middleware", exc_info=True)
            hits = data.get("hits")
            if isinstance(hits, list):
                for hit in hits:
                    if not isinstance(hit, dict):
                        continue
                    citation = hit.get("citation") if isinstance(hit.get("citation"), dict) else hit
                    doc_id = citation.get("document_id") if isinstance(citation, dict) else None
                    if isinstance(doc_id, str):
                        document_ids.append(doc_id)
    if not statuses and not packs:
        return None, None, document_ids

    pack = _merge_evidence_packs(packs)
    if pack is not None and pack.items:
        # A supported pack remains supported even when a later exploratory
        # query returned no rows. This distinguishes "one query missed" from
        # "the corpus has no usable evidence".
        status = "supported" if "supported" in statuses else next(
            (value for value in statuses if value not in {"insufficient", "empty"}),
            "supported",
        )
    else:
        status = statuses[0] if statuses else None
    return status, pack, list(dict.fromkeys(document_ids))


class EvidenceRefusalMiddleware(AgentMiddleware[AgentState]):
    """Replace unsupported historical answers with the product refusal contract."""

    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:  # noqa: ARG002
        return self._apply(state)

    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:  # noqa: ARG002
        return self._apply(state)

    def _apply(self, state: AgentState) -> dict[str, Any] | None:
        messages = list(state.get("messages") or [])
        if not messages or not isinstance(messages[-1], AIMessage):
            return None
        message = messages[-1]
        if _has_tool_calls(message):
            return None

        status, pack, document_ids = _latest_retrieval_context(messages)
        if status is None and pack is None:
            return None

        query = _latest_user_query(messages)
        refusal = evaluate_refusal(
            query=query or "（未捕获用户问题）",
            search_status=status,
            pack=pack,
            document_ids=document_ids,
            allow_inferred_answer=True,
        )
        text = _message_text(message.content) or ""
        answer_text = _visible_answer(message.content)
        low_grade_only = refusal.decision.reason is RefusalReason.LOW_GRADE_ONLY
        must_rewrite = refusal.decision.should_refuse
        nonexistence = is_historical_nonexistence_claim(text)

        if not must_rewrite and not low_grade_only and not nonexistence:
            return None

        message = _preserve_reasoning(message)
        if must_rewrite:
            supplement = _guard_unverified_supplement(answer_text)
            replacement = refusal.text
            if supplement:
                replacement += "\n\n补充分析（以下内容未被当前本地文献核验）：\n" + supplement
            updated = _set_message_text(message, replacement)
        elif low_grade_only:
            supplement = _guard_unverified_supplement(answer_text)
            replacement = (
                "当前检索到的材料均为 D/E/U 级或待复核来源，暂无经复核的明确记载。"
                "以下内容保留为补充分析，不作为已核定史实："
            )
            if supplement:
                replacement += "\n\n" + supplement
            updated = _set_message_text(message, replacement)
        else:
            # Soft guard: strip nonexistence overclaim while keeping answer body.
            guarded = answer_text + "\n\n说明：当前检索未支持“历史上不存在”之类绝对判断；未找到记载不等于历史上不存在。"
            updated = _set_message_text(message, guarded)

        metadata = dict(updated.response_metadata or {})
        metadata["refusal_validation"] = {
            "should_refuse": refusal.decision.should_refuse,
            "reason": refusal.decision.reason.value,
            "nonexistence_claim_blocked": nonexistence,
            "message": refusal.message,
        }
        updated = updated.model_copy(update={"response_metadata": metadata})
        return {"messages": [updated]}
