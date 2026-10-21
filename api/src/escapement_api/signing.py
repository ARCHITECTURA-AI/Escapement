"""Certificate signing keys. The private key lives outside the repository:
in ESCAPEMENT_SIGNING_KEY when hosted, or generated into the local data
directory in open-source mode. Public halves are served at
/.well-known/escapement-keys.json with key ids so keys can rotate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from escapement_engine.certificate import generate_keypair, key_id_for, keyset_entry, public_from_private, sign_certificate
from sqlalchemy import select

from .config import Settings
from .db import Database
from .models import SigningKey


class Signer:
    def __init__(self, settings: Settings, db: Database) -> None:
        private = settings.signing_key
        if not private:
            if settings.mode == "public":
                raise RuntimeError("ESCAPEMENT_SIGNING_KEY must be set in public mode")
            path = Path(settings.data_dir) / "keys" / "signing_key"
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                private = path.read_text().strip()
            else:
                private, _ = generate_keypair()
                path.write_text(private)
                path.chmod(0o600)
        self._private = private
        self.public = public_from_private(private)
        self.key_id = key_id_for(self.public)
        self.created = settings.signing_key_created
        self.db = db

    def register(self) -> None:
        with self.db.owner_session() as s:
            if s.get(SigningKey, self.key_id) is None:
                s.add(SigningKey(key_id=self.key_id, public_key=self.public, created=self.created))

    def sign(self, body: dict[str, Any]) -> dict[str, Any]:
        return sign_certificate(body, self._private, self.key_id)

    def keyset(self) -> dict[str, Any]:
        with self.db.api_session() as s:
            rows = s.execute(select(SigningKey).order_by(SigningKey.created)).scalars().all()
            keys = [keyset_entry(r.public_key, r.created, r.retired) for r in rows]
        if not any(k["key_id"] == self.key_id for k in keys):
            keys.append(keyset_entry(self.public, self.created))
        return {"issuer": "Escapement", "keys": keys}
