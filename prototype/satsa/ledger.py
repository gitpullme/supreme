"""Tamper-evident hash-chain audit ledger (SHA-256, Merkle-style chaining).

One JSON object per line: {seq, ts, event, payload, prev_hash, hash}.
Any edit of history breaks the chain -> independently verifiable
(PS REQ 11-14). Multi-node future: same event schema ports to
Hyperledger Fabric; single-node v0 needs no network at all.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, path: str):
        self.path = path
        if not os.path.exists(path):
            open(path, "w").close()

    def _last_hash(self) -> str:
        prev = "GENESIS"
        if os.path.getsize(self.path):
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        prev = json.loads(line)["hash"]
        return prev

    def append(self, event: str, payload: dict) -> dict:
        prev = self._last_hash()
        seq = 0
        if os.path.getsize(self.path):
            with open(self.path) as f:
                seq = sum(1 for ln in f if ln.strip())
        body = json.dumps({"seq": seq, "ts": _utcnow(), "event": event,
                           "payload": payload, "prev_hash": prev},
                          sort_keys=True, default=str)
        digest = hashlib.sha256((prev + body).encode()).hexdigest()
        rec = json.loads(body)
        rec["hash"] = digest
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
        return rec

    def read_all(self) -> list:
        out = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def verify(self) -> tuple[bool, str]:
        prev = "GENESIS"
        with open(self.path) as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                h = rec.pop("hash")
                body = json.dumps(rec, sort_keys=True, default=str)
                expect = hashlib.sha256((prev + body).encode()).hexdigest()
                if expect != h or rec["prev_hash"] != prev:
                    return False, f"chain broken at seq {i}"
                prev = h
        return True, f"ok ({i + 1 if 'i' in dir() else 0} events)"
