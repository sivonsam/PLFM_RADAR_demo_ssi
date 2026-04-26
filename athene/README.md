# Athene demo workspace

This folder contains the Athene demo scaffold:
- A simulator that emits synthetic events (JSON Lines)
- A simple ingest step that writes the event stream to NDJSON

Next increments:
1) Replace file-based ingest with a managed event stream
2) Add enrichment/filtering
3) Publish selected events to a GIS/visualisation endpoint
