from __future__ import annotations

import asyncio
import json

import httpx
from wu_culture.ocr import OcrPageImage, OpenAICompatibleVisionOcrProvider


def test_vision_provider_sends_page_and_parses_structured_ocr_result():
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "raw_text": "木渎",
                                    "mean_confidence": 0.93,
                                    "rotation_degrees": 90,
                                    "regions": [
                                        {
                                            "text": "木渎",
                                            "confidence": 0.93,
                                            "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    provider = OpenAICompatibleVisionOcrProvider(
        base_url="https://llm.example/v1",
        api_key="test-secret",
        model="vision-model",
        client=client,
    )
    page = OcrPageImage(page_number=3, content=b"\x89PNG\r\n\x1a\npage", width=100, height=200, sha256="a" * 64)

    result = asyncio.run(provider.recognize(page, languages=("zh-Hans", "zh-Hant")))
    asyncio.run(client.aclose())

    assert result.raw_text == "木渎"
    assert result.rotation_degrees == 90
    assert result.regions[0].bounding_box.x == 0.1
    payload = json.loads(requests[0].content)
    assert requests[0].url == "https://llm.example/v1/chat/completions"
    assert payload["model"] == "vision-model"
    assert payload["response_format"]["type"] == "json_schema"
    schema = payload["response_format"]["json_schema"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "zh-Hans, zh-Hant" in payload["messages"][0]["content"][0]["text"]


def test_vision_provider_supports_responses_api_structured_output():
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "raw_text": "MUDU 123",
                                        "mean_confidence": 0.97,
                                        "rotation_degrees": 0,
                                        "regions": [
                                            {
                                                "text": "MUDU 123",
                                                "confidence": 0.97,
                                                "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.2},
                                            }
                                        ],
                                    }
                                ),
                            }
                        ],
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    provider = OpenAICompatibleVisionOcrProvider(
        base_url="https://llm.example/v1",
        api_key="test-secret",
        model="vision-model",
        api_mode="responses",
        client=client,
    )
    page = OcrPageImage(page_number=1, content=b"\x89PNG\r\n\x1a\npage", width=100, height=200, sha256="a" * 64)

    result = asyncio.run(provider.recognize(page, languages=("en",)))
    asyncio.run(client.aclose())

    assert result.raw_text == "MUDU 123"
    payload = json.loads(requests[0].content)
    assert requests[0].url == "https://llm.example/v1/responses"
    assert payload["text"]["format"]["name"] == "ocr_page"
    assert payload["input"][0]["content"][1]["type"] == "input_image"
