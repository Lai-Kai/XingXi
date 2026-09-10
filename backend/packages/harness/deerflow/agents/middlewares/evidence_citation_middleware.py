"""Sanitize Xingxi answers so inline citations only reference evidence-pack IDs."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.runtime import Runtime
from wu_culture.citations import validate_answer_citations
from wu_culture.citations.validator import (
    contract_from_allowed_ids,
    extract_evidence_ids_from_tool_payloads,
)
from wu_culture.evidence_pack import EvidencePack

logger = logging.getLogger(__name__)


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


def _has_tool_calls(message: AIMessage) -> bool:
    if message.tool_calls or getattr(message, "invalid_tool_calls", None):
        return True
    additional_kwargs = message.additional_kwargs or {}
    return bool(additional_kwargs.get("tool_calls") or additional_kwargs.get("function_call"))


def _extract_contracts_from_messages(messages: list[Any]):
    payloads: list[object] = []
    packs: list[EvidencePack] = []
    locators: dict[str, dict[str, object]] = {}

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        text = _message_text(message.content)
        if not text:
            continue
        payloads.append(text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        pack_data = data.get("evidence_pack") if isinstance(data, dict) else None
        if isinstance(pack_data, dict):
            try:
                pack = EvidencePack.model_validate(pack_data)
                packs.append(pack)
                for item in pack.items:
                    locators[item.evidence_id] = item.model_dump(mode="json")
            except Exception:
                logger.debug("Skipping invalid evidence_pack payload", exc_info=True)

    if packs:
        # Use the latest pack; numbers stay local to that retrieval turn.
        return packs[-1], None

    ids = extract_evidence_ids_from_tool_payloads(payloads)
    if not ids:
        return None, None
    return None, contract_from_allowed_ids(ids, locators=locators)


class EvidenceCitationMiddleware(AgentMiddleware[AgentState]):
    """Drop invented evidence IDs and renumber valid citations after model output."""

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
        text = _message_text(message.content)
        if text is None or "evidence://" not in text.lower() and "[citation:" not in text.lower():
            return None

        pack, contract = _extract_contracts_from_messages(messages)
        if pack is None and contract is None:
            # No retrieval context: strip any evidence:// citations to avoid fabricated locators.
            result = validate_answer_citations(text, contract=None)
        elif pack is not None:
            result = validate_answer_citations(text, pack=pack)
        else:
            result = validate_answer_citations(text, contract=contract)

        if not result.rewritten and not result.rejected:
            return None

        updated = _set_message_text(message, result.sanitized_text)
        metadata = dict(updated.response_metadata or {})
        metadata["citation_validation"] = {
            "rewritten": result.rewritten,
            "rejected_count": len(result.rejected),
            "valid_count": len(result.valid_refs),
            "rejected": [item.model_dump(mode="json") for item in result.rejected],
        }
        updated = updated.model_copy(update={"response_metadata": metadata})
        return {"messages": [updated]}
