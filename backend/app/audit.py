"""Append-only log of order events and trades, one JSON object per line."""
import json
import time
from pathlib import Path


class AuditLog:
    def __init__(self, directory: Path | None):
        self._seq = 0
        self._file = None
        self.path: Path | None = None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"audit-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
            self._file = self.path.open("a", buffering=1)  # line buffered

    def write(self, event: str, **fields) -> None:
        if self._file is None:
            return
        self._seq += 1
        record = {"seq": self._seq, "ts": round(time.time(), 6), "event": event, **fields}
        self._file.write(json.dumps(record, separators=(",", ":")) + "\n")

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
