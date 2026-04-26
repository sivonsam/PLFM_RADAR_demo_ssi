#!/usr/bin/env python3
import json, random, time, uuid
from datetime import datetime, timezone

# Athene demo: simulated targets emitted as JSON Lines (one event per line).
# Output can be piped to an ingest component (file, message bus, event stream, etc.).

def make_target():
    lat = 60.20 + random.uniform(-0.08, 0.08)
    lon = 25.00 + random.uniform(-0.12, 0.12)
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "target",
        "source": "athene_simulator",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target": {
            "target_id": random.randint(1000, 9999),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "speed_mps": round(random.uniform(1.0, 35.0), 2),
            "heading_deg": round(random.uniform(0, 359.9), 1),
            "confidence": round(random.uniform(0.70, 0.99), 2),
        },
        "meta": {"schema_version": "0.1"}
    }

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--rate", type=float, default=1.0, help="events per second")
    p.add_argument("--count", type=int, default=0, help="0 = run forever")
    args = p.parse_args()

    interval = 1.0 / max(args.rate, 0.001)
    i = 0
    while True:
        print(json.dumps(make_target()))
        i += 1
        if args.count and i >= args.count:
            break
        time.sleep(interval)

if __name__ == "__main__":
    main()
