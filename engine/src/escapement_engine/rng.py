"""A counter-mode SHA-256 stream. Python's `random` module is not promised to
be stable across versions, and generation must reproduce from seed plus
template and engine versions forever (section 12.1)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class SeededRandom:
    def __init__(self, *parts: str) -> None:
        self._key = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
        self._counter = 0
        self._buffer = b""

    def _bytes(self, n: int) -> bytes:
        while len(self._buffer) < n:
            block = hashlib.sha256(self._key + self._counter.to_bytes(8, "big")).digest()
            self._counter += 1
            self._buffer += block
        out, self._buffer = self._buffer[:n], self._buffer[n:]
        return out

    def u32(self) -> int:
        return int.from_bytes(self._bytes(4), "big")

    def below(self, n: int) -> int:
        """Uniform integer in [0, n) by rejection sampling."""
        if n <= 0:
            raise ValueError("n must be positive")
        limit = (2**32 // n) * n
        while True:
            x = self.u32()
            if x < limit:
                return x % n

    def between(self, lo: int, hi: int) -> int:
        """Uniform integer in [lo, hi]."""
        return lo + self.below(hi - lo + 1)

    def choice(self, items: Sequence[T]) -> T:
        return items[self.below(len(items))]

    def shuffle(self, items: list[T]) -> list[T]:
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.below(i + 1)
            out[i], out[j] = out[j], out[i]
        return out

    def sample(self, items: Sequence[T], k: int) -> list[T]:
        return self.shuffle(list(items))[:k]

    def digits(self, n: int) -> str:
        return "".join(str(self.below(10)) for _ in range(n))
