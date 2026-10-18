"""Map asset storage schema, registered for bootstrap and safe autogeneration.

Application services own the workflows; the harness owns table definitions.
Separate metadata also supports small isolated repository tests.
"""

from sqlalchemy import Column, Float, Index, Integer, MetaData, String, Table, Text

from deerflow.persistence.base import Base

job_metadata = MetaData()
reconstruction_jobs = Table(
    "map_reconstruction_jobs",
    job_metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(255), nullable=False),
    Column("point_id", String(255)),
    Column("request_key", String(128), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("revision", Integer, nullable=False, default=0, server_default="0"),
    Column("data_json", Text, nullable=False),
    Index("uq_map_reconstruction_request", "owner_id", "request_key", unique=True),
    Index("ix_map_reconstruction_point", "point_id", "created_at"),
)


point_metadata = MetaData()
custom_points = Table(
    "map_custom_points",
    point_metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(255), nullable=False),
    Column("request_key", String(128), nullable=False),
    Column("name", String(120), nullable=False),
    Column("lon", Float, nullable=False),
    Column("lat", Float, nullable=False),
    Column("created_at", String(64), nullable=False),
    Index("uq_map_custom_point_request", "owner_id", "request_key", unique=True),
)


reconstruction_jobs.to_metadata(Base.metadata)
custom_points.to_metadata(Base.metadata)
