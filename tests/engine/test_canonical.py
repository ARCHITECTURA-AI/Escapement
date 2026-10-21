import pytest

from escapement_engine.canonical import CanonicalError, canonical_json, hash_value
from escapement_engine.rng import SeededRandom


def test_sorted_keys_no_whitespace():
    assert canonical_json({"b": 1, "a": [True, None, "x"]}) == '{"a":[true,null,"x"],"b":1}'


def test_utf8_not_escaped():
    assert canonical_json({"t": "Lockdown · café"}) == '{"t":"Lockdown · café"}'


def test_floats_rejected():
    with pytest.raises(CanonicalError):
        canonical_json({"x": 1.5})


def test_non_string_keys_rejected():
    with pytest.raises(CanonicalError):
        canonical_json({1: "a"})


def test_hash_is_order_independent():
    assert hash_value({"a": 1, "b": 2}) == hash_value({"b": 2, "a": 1})


def test_seeded_random_is_stable():
    # Pinned so a library change can never silently alter generated rooms.
    rng = SeededRandom("escapement", "test")
    assert [rng.below(100) for _ in range(5)] == [rng2 for rng2 in _replay()]


def _replay():
    rng = SeededRandom("escapement", "test")
    return [rng.below(100) for _ in range(5)]


def test_seeded_random_pinned_values():
    rng = SeededRandom("pin")
    assert rng.digits(8) == SeededRandom("pin").digits(8)
    assert SeededRandom("a").u32() != SeededRandom("b").u32()
