"""Run Certificates (section 14.1) and offline verification (14.2).

The server signs the canonical JSON of every certificate field except the
signature with Ed25519. Public keys are published with key ids, so keys can
rotate without breaking old certificates.

Verification levels:

* ``signature``  the certificate is signed by a published Escapement key and
  unmodified;
* ``chain``      a replay file's hash chain recomputes to the certified final
  hash;
* ``full``       the replay re-simulates through the pinned engine against the
  room manifest. Ranked manifests stay sealed until the season closes, so for
  them ``chain`` is the most anyone else can check before then.

A certificate proves that these actions solved (or failed) this room inside the
budget, on the Escapement server. It does not prove who or what chose them.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from ..canonical import canonical_bytes
from ..replay import resimulate, verify_chain
from ..schemas.manifest import RoomManifest
from ..version import CERTIFICATE_FORMAT

PROVES = "These actions were applied by the Escapement engine to this room instance, inside the stated budget, on the Escapement server, with the stated outcome."
DOES_NOT_PROVE = "Who or what chose the actions, or which model ran. Agent name, model, framework, memory strategy, tokens and cost are self-reported unless marked verified."

SELF_REPORTED_FIELDS = (
    "agent.model",
    "agent.framework",
    "agent.memory",
    "usage.tokens_in",
    "usage.tokens_out",
    "usage.cost_usd_micros",
    "usage.model_decisions",
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def generate_keypair() -> tuple[str, str]:
    """Return (private_seed_b64, public_key_b64)."""
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _b64(private), _b64(public)


def public_from_private(private_b64: str) -> str:
    key = Ed25519PrivateKey.from_private_bytes(_unb64(private_b64))
    return _b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def key_id_for(public_b64: str) -> str:
    return "ek_" + hashlib.sha256(_unb64(public_b64)).hexdigest()[:16]


def signing_payload(cert: dict[str, Any]) -> bytes:
    return canonical_bytes({k: v for k, v in cert.items() if k != "signature"})


def sign_certificate(body: dict[str, Any], private_b64: str, key_id: str | None = None) -> dict[str, Any]:
    if "signature" in body:
        raise ValueError("body must not contain a signature")
    public_b64 = public_from_private(private_b64)
    cert = dict(body)
    cert["format"] = CERTIFICATE_FORMAT
    cert["key_id"] = key_id or key_id_for(public_b64)
    key = Ed25519PrivateKey.from_private_bytes(_unb64(private_b64))
    cert["signature"] = _b64(key.sign(signing_payload(cert)))
    return cert


def keyset_entry(public_b64: str, created: str, retired: str | None = None) -> dict[str, Any]:
    return {"key_id": key_id_for(public_b64), "alg": "Ed25519", "public_key": public_b64, "created": created, "retired": retired}


@dataclass
class VerifyReport:
    signature_valid: bool
    level: str  # "none", "signature", "chain", "full"
    key_id: str | None = None
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.signature_valid and not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "signature_valid": self.signature_valid,
            "level": self.level,
            "key_id": self.key_id,
            "problems": self.problems,
            "notes": self.notes,
        }


def verify_signature(cert: dict[str, Any], keyset: dict[str, Any]) -> tuple[bool, str]:
    key_id = cert.get("key_id")
    sig = cert.get("signature")
    if not key_id or not sig:
        return False, "certificate has no key id or signature"
    if cert.get("format") != CERTIFICATE_FORMAT:
        return False, f"unsupported certificate format {cert.get('format')!r}"
    entry = next((k for k in keyset.get("keys", []) if k.get("key_id") == key_id), None)
    if entry is None:
        return False, f"key {key_id} is not in the published key set"
    if key_id_for(entry["public_key"]) != key_id:
        return False, "key set entry does not match its key id"
    try:
        Ed25519PublicKey.from_public_bytes(_unb64(entry["public_key"])).verify(_unb64(sig), signing_payload(cert))
    except (InvalidSignature, ValueError):
        return False, "signature does not match the certificate contents"
    return True, ""


def verify(
    cert: dict[str, Any],
    keyset: dict[str, Any],
    replay: dict[str, Any] | None = None,
    manifest: RoomManifest | None = None,
) -> VerifyReport:
    ok, reason = verify_signature(cert, keyset)
    report = VerifyReport(signature_valid=ok, level="signature" if ok else "none", key_id=cert.get("key_id"))
    if not ok:
        report.problems.append(reason)
        return report
    if replay is None:
        report.notes.append("Signature checked offline. Pass a replay file to also check the hash chain.")
        return report
    if replay.get("run_id") != cert.get("run_id"):
        report.problems.append("replay is for a different run")
        return report
    chain = verify_chain(replay)
    if not chain.ok:
        report.problems.append(f"hash chain: {chain.reason}" + (f" at step {chain.first_bad_seq}" if chain.first_bad_seq else ""))
        return report
    if chain.final_hash != cert.get("final_chain_hash"):
        report.problems.append("replay's final hash differs from the certified final hash")
        return report
    if replay["room"]["instance_hash"] != cert.get("room", {}).get("instance_hash"):
        report.problems.append("replay is for a different room instance")
        return report
    report.level = "chain"
    if manifest is None:
        report.notes.append("Chain verified. Full re-simulation needs the room manifest (sealed until the season closes for ranked rooms).")
        return report
    sim = resimulate(replay, manifest)
    if not sim.ok:
        report.problems.extend(f"re-simulation: {m}" for m in sim.mismatches)
        return report
    if sim.outcome != cert.get("outcome"):
        report.problems.append("re-simulated outcome differs from the certified outcome")
        return report
    report.level = "full"
    return report


__all__ = [
    "DOES_NOT_PROVE",
    "PROVES",
    "SELF_REPORTED_FIELDS",
    "VerifyReport",
    "generate_keypair",
    "key_id_for",
    "keyset_entry",
    "public_from_private",
    "sign_certificate",
    "signing_payload",
    "verify",
    "verify_signature",
]
