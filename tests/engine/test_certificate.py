"""Certificate tests (section 24.3): signature vectors, key rotation,
revoked and modified certificates (AC-10)."""

import copy

from escapement_engine.agents import HeuristicExplorer, run_local
from escapement_engine.certificate import (
    generate_keypair,
    key_id_for,
    keyset_entry,
    sign_certificate,
    signing_payload,
    verify,
    verify_signature,
)
from escapement_engine.replay import replay_from_episode

# A fixed test vector so any change to canonicalisation or signing is caught.
VECTOR_PRIVATE = "nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A="


def _body(replay, outcome):
    return {
        "certificate_id": "cert_test",
        "run_id": replay["run_id"],
        "issued_at": "2026-10-21T00:00:00Z",
        "room": {"instance_hash": replay["room"]["instance_hash"], "tier": "practice", "room_id": "practice"},
        "outcome": outcome,
        "final_chain_hash": replay["final_chain_hash"],
    }


def test_signature_vector_is_stable():
    cert = sign_certificate({"run_id": "r1", "outcome": "escaped", "actions_used": 17}, VECTOR_PRIVATE)
    again = sign_certificate({"run_id": "r1", "outcome": "escaped", "actions_used": 17}, VECTOR_PRIVATE)
    assert cert["signature"] == again["signature"]  # Ed25519 is deterministic
    assert signing_payload(cert) == signing_payload(again)
    assert cert["key_id"].startswith("ek_")


def test_full_verification_and_tampering(practice):
    run = run_local(HeuristicExplorer(), practice, "cert-run")
    replay = replay_from_episode(run.episode)
    priv, pub = generate_keypair()
    keys = {"keys": [keyset_entry(pub, "2026-10-01")]}
    cert = sign_certificate(_body(replay, run.outcome), priv)
    report = verify(cert, keys, replay, practice)
    assert report.ok and report.level == "full"
    assert verify(cert, keys).level == "signature"
    assert verify(cert, keys, replay).level == "chain"

    modified = copy.deepcopy(cert)
    modified["outcome"] = "escaped" if cert["outcome"] != "escaped" else "action_budget_exhausted"
    assert not verify(modified, keys).ok

    forged_replay = copy.deepcopy(replay)
    forged_replay["steps"] = forged_replay["steps"][:-1]
    assert not verify(cert, keys, forged_replay, practice).ok


def test_key_rotation_keeps_old_certificates_valid():
    old_priv, old_pub = generate_keypair()
    new_priv, new_pub = generate_keypair()
    old_cert = sign_certificate({"run_id": "a"}, old_priv)
    new_cert = sign_certificate({"run_id": "b"}, new_priv)
    keys = {"keys": [keyset_entry(old_pub, "2026-01-01", retired="2026-10-01"), keyset_entry(new_pub, "2026-10-01")]}
    assert verify_signature(old_cert, keys)[0]
    assert verify_signature(new_cert, keys)[0]
    assert old_cert["key_id"] == key_id_for(old_pub) != new_cert["key_id"]


def test_unknown_key_and_wrong_key_rejected():
    priv, pub = generate_keypair()
    other_priv, other_pub = generate_keypair()
    cert = sign_certificate({"run_id": "a"}, priv)
    assert not verify_signature(cert, {"keys": [keyset_entry(other_pub, "x")]})[0]
    spoof = dict(keyset_entry(other_pub, "x"), key_id=cert["key_id"])
    assert not verify_signature(cert, {"keys": [spoof]})[0]
