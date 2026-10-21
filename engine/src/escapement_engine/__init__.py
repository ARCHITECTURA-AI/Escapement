"""Escapement open core.

An agent does not escape because it says it escaped. It escapes only when its
actions satisfy the environment's rules.
"""

from .version import CERTIFICATE_FORMAT, ENGINE_VERSION, MANIFEST_FORMAT, PROTOCOL_VERSION, REPLAY_FORMAT

__all__ = ["CERTIFICATE_FORMAT", "ENGINE_VERSION", "MANIFEST_FORMAT", "PROTOCOL_VERSION", "REPLAY_FORMAT"]
__version__ = ENGINE_VERSION
