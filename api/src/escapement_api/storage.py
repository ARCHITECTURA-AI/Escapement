"""Replay storage: S3-compatible object storage when hosted, the local
filesystem in open-source mode (19.1). The database transitions remain the
source of truth; stored replays are an immutable, hashed export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from escapement_engine.canonical import sha256_hex


class ReplayStore(Protocol):
    def put(self, run_id: str, replay: dict[str, Any]) -> str: ...
    def get(self, key: str) -> dict[str, Any] | None: ...
    def delete(self, key: str) -> None: ...


class FilesystemStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, run_id: str, replay: dict[str, Any]) -> str:
        data = json.dumps(replay, ensure_ascii=False, separators=(",", ":"))
        key = f"{run_id}.json"
        (self.root / key).write_text(data, "utf-8")
        (self.root / f"{run_id}.sha256").write_text(sha256_hex(data))
        return key

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.root / key
        if not path.exists():
            return None
        data = path.read_text("utf-8")
        digest_path = path.with_suffix(".sha256")
        if digest_path.exists() and digest_path.read_text().strip() != sha256_hex(data):
            return None  # corrupted artifact: fall back to the database
        return json.loads(data)

    def delete(self, key: str) -> None:
        for p in (self.root / key, (self.root / key).with_suffix(".sha256")):
            p.unlink(missing_ok=True)


class S3Store:  # pragma: no cover - needs a bucket
    def __init__(self, bucket: str, prefix: str = "replays/", endpoint_url: str | None = None) -> None:
        import boto3

        self.client = boto3.client("s3", endpoint_url=endpoint_url)
        self.bucket = bucket
        self.prefix = prefix

    def put(self, run_id: str, replay: dict[str, Any]) -> str:
        data = json.dumps(replay, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        key = f"{self.prefix}{run_id}.json"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType="application/json",
            Metadata={"sha256": sha256_hex(data)},
        )
        return key

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        data = obj["Body"].read()
        if obj.get("Metadata", {}).get("sha256") not in (None, sha256_hex(data)):
            return None
        return json.loads(data)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
