from __future__ import annotations

import asyncio

import httpx

from app.gateway.routers.map_points import RoutePlanRequest, fetch_osrm_route


def test_osrm_route_geometry_is_returned() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/route/v1/driving/" in str(request.url)
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "distance": 1250.5,
                        "duration": 420.0,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[120.5, 31.25], [120.51, 31.26]],
                        },
                    }
                ]
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch_osrm_route(
                RoutePlanRequest(
                    coordinates=(
                        {"lon": 120.5, "lat": 31.25, "name": "起点"},
                        {"lon": 120.51, "lat": 31.26, "name": "终点"},
                    )
                ),
                client=client,
                base_url="https://routing.example",
            )
        assert result.routing_status == "routed"
        assert result.route_kind == "road"
        assert result.distance_meters == 1250.5
        assert len(result.coordinates) == 2

    asyncio.run(run())


def test_route_provider_failure_returns_explicit_direct_line_fallback() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(503))
        ) as client:
            result = await fetch_osrm_route(
                RoutePlanRequest(
                    coordinates=(
                        {"lon": 120.5, "lat": 31.25},
                        {"lon": 120.51, "lat": 31.26},
                    )
                ),
                client=client,
                base_url="https://routing.example",
            )
        assert result.routing_status == "unavailable"
        assert result.route_kind == "stop_order"
        assert result.distance_meters is None
        assert "direct line" in result.message

    asyncio.run(run())
