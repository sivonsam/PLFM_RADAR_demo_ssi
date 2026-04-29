"""
Athene demo — Radar event schema v1.0

Every event emitted by the simulator (or any real sensor adapter) must
conform to this schema.  The event_id UUID is the unique key that flows
through the full pipeline:

    Simulator → Event Hub → Eventhouse (KQL) → OneLake → ArcGIS Feature Layer

Track types
-----------
confirmed   Radar track correlated with an AIS transponder signal.
dark        Radar return with NO matching AIS signal — primary anomaly.
unknown     New / uncorrelated track; correlation still in progress.

Vessel types
------------
ferry | cargo | small_craft | patrol | dark | unknown
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"


@dataclass
class SeaState:
    wave_height_m: float | None = None
    wind_speed_mps: float | None = None
    wind_dir_deg: float | None = None
    station_id: str | None = None


@dataclass
class TargetFields:
    target_id: str
    track_type: str        # "confirmed" | "dark" | "unknown"
    vessel_type: str       # "ferry" | "cargo" | "small_craft" | "patrol" | "dark" | "unknown"
    lat: float
    lon: float
    speed_mps: float
    heading_deg: float
    confidence: float      # 0.0 - 1.0
    mmsi: int | None = None
    vessel_name: str | None = None
    cog: float | None = None   # Course over ground from AIS (degrees)


@dataclass
class Meta:
    schema_version: str = SCHEMA_VERSION
    correlated: bool = False       # True when radar track matched to live AIS
    scenario: str | None = None  # "ferry_route" | "cargo_transit" | "dark_target" | …
    source_detail: str | None = None


@dataclass
class RadarEvent:
    event_id: str
    event_type: str        # "radar_track" | "ais_vessel"
    source: str            # "athene_sim" | "digitraffic_ais" | "athene_sim+ais"
    timestamp_utc: str     # ISO-8601 UTC
    session_id: str        # Groups all events in one demo run
    target: TargetFields
    sea_state: SeaState | None
    meta: Meta

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["sea_state"] and all(v is None for v in d["sea_state"].values()):
            d["sea_state"] = None
        return d

    @staticmethod
    def make_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()  # noqa: UP017
