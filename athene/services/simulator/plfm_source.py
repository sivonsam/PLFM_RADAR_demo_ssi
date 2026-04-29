"""
PLFM (Pulse Linear FM) radar event source for Athene demo.

Simulates multiple AERIS-10 radar sites along the Tallinn-Uurainen corridor
(~338 km, roughly 59.5 N to 62.5 N).  Each site rotates its antenna beam
(like the AERIS-10 stepper motor) and produces authentic AERIS-10-style
detections: range bin, Doppler bin, SNR, and I/Q values.

Detections are then geo-projected to lat/lon using the radar position,
current azimuth, and AERIS-10E range parameters (20 km, 64 range bins).

Radar parameters match AERIS-10 hardware (from radar_protocol.py):
  NUM_RANGE_BINS   = 64
  NUM_DOPPLER_BINS = 32
  Range resolution = MAX_RANGE / NUM_RANGE_BINS  (20 km / 64 ≈ 312.5 m)
  Doppler res      = ~0.52 m/s per bin (X-band 10.5 GHz, 32 bins)
  Rotation speed   = 6 RPM (stepper motor), 1° per step → 360 steps/revolution

Output: RadarEvent objects with event_type="plfm_radar", ready to merge
into the Athene SSE stream alongside AIS-correlated simulator tracks.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

from schema import Meta, RadarEvent, SeaState, TargetFields

# ── AERIS-10 hardware constants ───────────────────────────────────────────────
MAX_RANGE_M        = 20_000        # AERIS-10E extended range
NUM_RANGE_BINS     = 64
NUM_DOPPLER_BINS   = 32
RANGE_RES_M        = MAX_RANGE_M / NUM_RANGE_BINS          # 312.5 m
DOPPLER_RES_MPS    = 0.52                                   # m/s per bin
MAX_SPEED_MPS      = (NUM_DOPPLER_BINS / 2) * DOPPLER_RES_MPS  # ±8.32 m/s
BEAM_WIDTH_DEG     = 10.0          # demo beam width — wider for visible detections
ROTATION_DEG_STEP  = 5.0           # faster sweep for demo
EARTH_R            = 6_371_000.0

# ── Radar sites along Tallinn-Uurainen corridor ───────────────────────────────
# lat, lon, site_id, description, min_range_bin (clutter exclusion)
RADAR_SITES: list[tuple] = [
    (59.500, 24.740, "SITE_TALLINN",  "Tallinn coast",        3),
    (60.170, 24.940, "SITE_HELSINKI", "Helsinki (HEL-RAD)",   3),
    (61.500, 25.050, "SITE_TAMPERE",  "Tampere corridor",     4),
    (62.530, 25.170, "SITE_UURAINEN", "Uurainen",             4),
]


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _geo_project(
    radar_lat: float, radar_lon: float,
    azimuth_deg: float, slant_range_m: float,
) -> tuple[float, float]:
    """Project a radar detection to lat/lon."""
    d   = slant_range_m / EARTH_R
    lat1 = math.radians(radar_lat)
    lon1 = math.radians(radar_lon)
    az   = math.radians(azimuth_deg)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d)
        + math.cos(lat1) * math.sin(d) * math.cos(az)
    )
    lon2 = lon1 + math.atan2(
        math.sin(az) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return round(math.degrees(lat2), 6), round(math.degrees(lon2), 6)


def _iq_from_snr(snr_db: float) -> tuple[int, int]:
    """Produce a plausible I/Q sample pair for a given SNR (dB)."""
    amplitude = 10 ** (snr_db / 20.0) * 100
    noise     = random.gauss(0, 30)
    phase     = random.uniform(0, 2 * math.pi)
    i_val     = int(amplitude * math.cos(phase) + noise)
    q_val     = int(amplitude * math.sin(phase) + noise)
    return max(-32768, min(32767, i_val)), max(-32768, min(32767, q_val))


# ── Per-site rotating scanner ─────────────────────────────────────────────────

@dataclass
class RadarSite:
    lat: float
    lon: float
    site_id: str
    description: str
    min_range_bin: int
    azimuth_deg: float = field(default_factory=lambda: random.uniform(0, 360))
    _scan_targets: list[dict] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        # Seed a larger pool of targets for visible demo density
        self._scan_targets = [self._random_target() for _ in range(random.randint(6, 10))]

    def _random_target(self) -> dict:
        """A persistent synthetic target in this radar's coverage."""
        az    = random.uniform(0, 360)
        rbin  = random.randint(self.min_range_bin + 1, NUM_RANGE_BINS - 4)
        dbin  = random.randint(0, NUM_DOPPLER_BINS - 1)
        snr   = random.uniform(8, 28)       # dB
        lat, lon = _geo_project(self.lat, self.lon, az, rbin * RANGE_RES_M)
        return {
            "az": az, "range_bin": rbin, "doppler_bin": dbin,
            "snr_db": snr, "lat": lat, "lon": lon,
            "drift_az": random.uniform(-0.5, 0.5),    # deg/step
            "drift_range": random.choice([-1, 0, 0, 1]),
        }

    def step_and_detect(self) -> list[dict]:
        """
        Advance azimuth by one step; return a list of raw detections that
        fall within the current beam (± BEAM_WIDTH_DEG / 2).
        """
        self.azimuth_deg = (self.azimuth_deg + ROTATION_DEG_STEP) % 360

        # Drift targets slowly to simulate movement
        for t in self._scan_targets:
            t["az"]        = (t["az"] + t["drift_az"]) % 360
            t["range_bin"] = max(
                self.min_range_bin + 1,
                min(NUM_RANGE_BINS - 2, t["range_bin"] + t["drift_range"]),
            )
            t["lat"], t["lon"] = _geo_project(
                self.lat, self.lon, t["az"], t["range_bin"] * RANGE_RES_M
            )
            # Occasionally replace a target with a new one
            if random.random() < 0.002:
                self._scan_targets[self._scan_targets.index(t)] = self._random_target()

        detections = []
        for t in self._scan_targets:
            ang_diff = abs(((t["az"] - self.azimuth_deg + 180) % 360) - 180)
            if ang_diff > BEAM_WIDTH_DEG / 2:
                continue
            # Beam-pattern gain roll-off (sinc-squared approximation)
            gain = math.cos(math.pi * ang_diff / BEAM_WIDTH_DEG) ** 2
            effective_snr = t["snr_db"] * gain
            if effective_snr < 3.0:     # lowered CFAR threshold for demo
                continue
            i_val, q_val = _iq_from_snr(effective_snr)
            velocity_mps = (t["doppler_bin"] - NUM_DOPPLER_BINS / 2) * DOPPLER_RES_MPS
            detections.append({
                "site_id":       self.site_id,
                "radar_lat":     self.lat,
                "radar_lon":     self.lon,
                "azimuth_deg":   round(self.azimuth_deg, 1),
                "range_bin":     t["range_bin"],
                "range_m":       round(t["range_bin"] * RANGE_RES_M, 0),
                "doppler_bin":   t["doppler_bin"],
                "velocity_mps":  round(velocity_mps, 2),
                "snr_db":        round(effective_snr, 1),
                "i_val":         i_val,
                "q_val":         q_val,
                "target_lat":    t["lat"],
                "target_lon":    t["lon"],
            })
        return detections


# ── Build RadarEvent from a raw PLFM detection ────────────────────────────────

def _detection_to_event(det: dict, session_id: str, sea: SeaState | None) -> RadarEvent:
    speed_abs = abs(det["velocity_mps"])
    # Classify loosely by speed: slow = small_craft, medium = cargo, fast = ferry
    if speed_abs < 1.5:
        vessel_type = "small_craft"
    elif speed_abs < 5.0:
        vessel_type = "cargo"
    else:
        vessel_type = "ferry"

    track_id = f"{det['site_id']}_{det['range_bin']:02d}_{det['doppler_bin']:02d}"

    return RadarEvent(
        event_id=RadarEvent.make_id(),
        event_type="plfm_radar",
        source=f"aeris10_{det['site_id'].lower()}",
        timestamp_utc=RadarEvent.now_utc(),
        session_id=session_id,
        target=TargetFields(
            target_id=track_id,
            track_type="unknown",         # no AIS correlation yet
            vessel_type=vessel_type,
            lat=det["target_lat"],
            lon=det["target_lon"],
            speed_mps=speed_abs,
            heading_deg=det["azimuth_deg"],
            confidence=min(0.99, round(det["snr_db"] / 30.0, 2)),
            mmsi=None,
            vessel_name=None,
        ),
        sea_state=sea,
        meta=Meta(
            correlated=False,
            scenario="plfm_radar_detection",
            source_detail=(
                f"site={det['site_id']} az={det['azimuth_deg']}° "
                f"range_bin={det['range_bin']} "
                f"snr={det['snr_db']}dB "
                f"I={det['i_val']} Q={det['q_val']}"
            ),
        ),
    )


# ── Public generator ──────────────────────────────────────────────────────────

def plfm_event_stream(
    session_id: str,
    sea: SeaState | None = None,
) -> Iterator[RadarEvent]:
    """
    Infinite generator: advances each radar site one azimuth step,
    yields a RadarEvent for every detection found in the beam.

    Call this in a round-robin loop interleaved with the main simulator pool.
    """
    sites = [RadarSite(*s) for s in RADAR_SITES]
    while True:
        for site in sites:
            for det in site.step_and_detect():
                yield _detection_to_event(det, session_id, sea)
