"""One canonical point catalog for imports and map-bound reconstructions."""

from fastapi import Depends

from app.gateway.routers import map_points
from app.gateway.routers.custom_map_points import get_custom_points


async def get_model_points(source=Depends(map_points.get_versioned_catalog_source), custom=Depends(get_custom_points)):
    catalog = await map_points.get_map_catalog(source)
    # Preserve the browser's exact ID-based override order.
    return {point.id: point for point in [*map_points.POINTS, *catalog.points, *custom]}
