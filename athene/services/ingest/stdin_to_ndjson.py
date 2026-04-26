#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime

# Athene demo: reads JSON lines from stdin and appends to an NDJSON file.
# This is a placeholder for a real event stream / message bus.

def main():
    if len(sys.argv) < 2:
        print("Usage: stdin_to_ndjson.py <output_file.ndjson>", file=sys.stderr)
        sys.exit(2)

    out_path = Path(sys.argv[1])
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("a", encoding="utf-8") as f:
        for line in sys.stdin:
            line = line.strip()
            if line:
                f.write(line + "\n")

    print(f"[{datetime.now().isoformat()}] wrote events to {out_path}", file=sys.stderr)

if __name__ == "__main__":
    main()
