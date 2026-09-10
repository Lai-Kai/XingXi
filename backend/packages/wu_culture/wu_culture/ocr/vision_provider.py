from __future__ import annotations

import base64
from typing import Any, Literal

import httpx

from .service import OcrPageImage, OcrProviderPage


class OpenAICompatibleVisionOcrProvider:
    name = "openai-compatible-vision"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        api_mode: Literal["chat_completions", "responses"] = "chat_completions",
        timeout_seconds: float = 120,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self._api_mode = api_mode
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def recognize(self, page: OcrPageImage, *, languages: tuple[str, ...]) -> OcrProviderPage:
        prompt = (
            f"OCR page {page.page_number}. Expected languages: {', '.join(languages)}. "
            "Return all visible text in reading order, the clockwise rotation needed to make the page upright, "
            "and normalized [0,1] bounding boxes for every text region."
        )
        image_url = f"data:image/png;base64,{base64.b64encode(page.content).decode('ascii')}"
        payload = self._responses_payload(prompt, image_url) if self._api_mode == "responses" else self._chat_completions_payload(prompt, image_url)
        if self._client is not None:
            response = await self._post(self._client, payload)
        else:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await self._post(client, payload)
        response.raise_for_status()
        body = response.json()
        content = self._responses_text(body) if self._api_mode == "responses" else body["choices"][0]["message"]["content"]
        return OcrProviderPage.model_validate_json(content)

    def _chat_completions_payload(self, prompt: str, image_url: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "ocr_page",
                    "strict": True,
                    "schema": OcrProviderPage.model_json_schema(),
                },
            },
        }

    def _responses_payload(self, prompt: str, image_url: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "ocr_page",
                    "strict": True,
                    "schema": OcrProviderPage.model_json_schema(),
                }
            },
        }

    @staticmethod
    def _responses_text(body: dict[str, Any]) -> str:
        output_text = body.get("output_text")
        if isinstance(output_text, str):
            return output_text
        for output in body.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise ValueError("OCR Responses API result did not contain output_text")

    async def _post(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> httpx.Response:
        endpoint = "responses" if self._api_mode == "responses" else "chat/completions"
        return await client.post(
            f"{self._base_url}/{endpoint}",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
            timeout=self._timeout_seconds,
        )
