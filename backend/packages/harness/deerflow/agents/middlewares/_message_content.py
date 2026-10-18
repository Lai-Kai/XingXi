"""Read and replace visible response text while retaining non-text blocks."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


def message_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict) and part.get("type") in {"text", "output_text"} and isinstance(part.get("text"), str):
                pieces.append(part["text"])
        return "\n".join(pieces) if pieces else None
    return None


def set_message_text(message: AIMessage, text: str) -> AIMessage:
    content = message.content
    if isinstance(content, list):
        replaced = False
        new_parts: list[Any] = []
        for part in content:
            if isinstance(part, str) or (isinstance(part, dict) and part.get("type") in {"text", "output_text"}):
                if not replaced:
                    new_parts.append(text if isinstance(part, str) else {**part, "text": text})
                    replaced = True
            else:
                new_parts.append(part)
        if not replaced:
            new_parts.append({"type": "text", "text": text})
        return message.model_copy(update={"content": new_parts})
    return message.model_copy(update={"content": text})
