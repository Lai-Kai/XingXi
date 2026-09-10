from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

_ACTION = re.compile(
    r"(?:教我|告诉我(?:怎么|如何)|给我(?:步骤|教程|配方|代码)|具体(?:步骤|方法)|帮我(?:制作|攻击|入侵|盗取|骗取|跟踪)|"
    r"how\s+to|step[- ]by[- ]step|write\s+(?:malware|ransomware)|help\s+me\s+(?:hack|steal|make))",
    re.IGNORECASE,
)
_HARM = re.compile(
    r"(?:炸弹|爆炸物|自杀|自残|勒索软件|木马病毒|钓鱼网站|入侵(?:账号|系统|网站)|盗取(?:密码|账号|身份)|"
    r"诈骗话术|制毒|毒品配方|跟踪他人|定位他人|泄露隐私|"
    r"bomb|explosive|suicide|self[- ]harm|malware|ransomware|phishing|hack\s+(?:an?\s+)?account|steal\s+(?:a\s+)?password|make\s+drugs)",
    re.IGNORECASE,
)
_CRISIS = re.compile(r"(?:我想自杀|我想死|准备自杀|想要伤害自己|I\s+want\s+to\s+(?:die|kill\s+myself))", re.IGNORECASE)

_REFUSAL = "我不能提供会直接促成伤害、攻击、诈骗、制毒或侵犯隐私的可执行方法。可以改为讨论相关历史背景、法律与伦理、风险识别或防范措施。"
_CRISIS_RESPONSE = "听起来你现在可能正处在危险中。请先远离可能伤害自己的物品，并立即联系身边可信任的人、当地急救电话或心理危机干预服务；如果危险迫近，请直接拨打当地紧急电话。"


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part if isinstance(part, str) else str(part.get("text", ""))
            for part in content
            if isinstance(part, (str, dict))
        )
    return ""


def safety_response(messages: list[Any]) -> AIMessage | None:
    user_text = next(
        (_text(message.content) for message in reversed(messages) if isinstance(message, HumanMessage)),
        "",
    ).strip()
    if not user_text:
        return None
    if _CRISIS.search(user_text):
        return AIMessage(
            content=_CRISIS_RESPONSE,
            response_metadata={"xingxi_safety": {"blocked": True, "category": "self_harm_crisis"}},
        )
    if _ACTION.search(user_text) and _HARM.search(user_text):
        return AIMessage(
            content=_REFUSAL,
            response_metadata={"xingxi_safety": {"blocked": True, "category": "actionable_harm"}},
        )
    return None


class XingxiSafetyMiddleware(AgentMiddleware):
    """Deterministically stop actionable high-risk requests before the LLM call."""

    @staticmethod
    def _record(request: ModelRequest, response: AIMessage) -> None:
        context = getattr(request.runtime, "context", None)
        if not isinstance(context, dict):
            return
        journal = context.get("__run_journal")
        if journal is None:
            return
        try:
            journal.record_middleware(
                tag="xingxi_safety",
                name="XingxiSafetyMiddleware",
                hook="wrap_model_call",
                action="block_model_call",
                changes=response.response_metadata["xingxi_safety"],
            )
        except Exception:
            return

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        response = safety_response(list(request.messages))
        if response is not None:
            self._record(request, response)
            return response
        return handler(request)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage:
        response = safety_response(list(request.messages))
        if response is not None:
            self._record(request, response)
            return response
        return await handler(request)
