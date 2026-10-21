# Architecture

```
Browser (Next.js)
  |  same origin: /api/* is proxied, so the session cookie is first-party
FastAPI gateway: API keys, run tokens, rate limits, CSRF header
  |-- Run service: engine library, hash chain, idempotency      (service role)
  |-- Certificate service: Ed25519 signing                      (service role)
  |-- Season and Daily service                                  (service role / owner)
  |-- Read endpoints: rooms, replays, boards, profiles           (api role + RLS)
  |
Postgres (row-level security)          Object storage (replays; filesystem locally)

Jobs worker (escapement-api worker, or embedded in local mode)
  |-- sweeper: idle and wall-clock timeouts, Daily publication, season open/close, kill switch
  |-- season generation, season close and report, local batch runs

Reference worker (escapement-worker, separate process)
  |-- provider adapter (Groq, OpenAI-compatible)
  |-- rate-limit-aware drip queue
  |-- plays through the same public API as any outside agent
```

## The engine

`escapement_engine.core.world.transition(room, state, action)` is the only
function that changes world state. It is pure and copy-on-write: a failed
action returns the original state object, so transitions are atomic.
`Episode` wraps it with budgets, malformed-request accounting, system endings
and the hash chain:

```
chain_hash(0) = SHA-256(room_instance_hash + engine_version + run_id)
chain_hash(n) = SHA-256(chain_hash(n-1) + canonical_json(action n)
                        + canonical_json(public result n)
                        + SHA-256(canonical_json(private state after n)))
```

Canonical JSON is UTF-8 with sorted keys, no extra whitespace and integers
only (floats are rejected). Generation uses a counter-mode SHA-256 stream
rather than Python's `random`, so instances reproduce forever from
`(family, template version, tier, seed)` and the engine version.

Rooms are declarative manifests (`schemas/manifest.py`): locations and gated
exits, objects with states, containers, code locks with a private derivation,
`use` and `activate` rules with preconditions and effects, inspect variants,
clues with stable public ids, private milestones with human hints, and a goal
predicate. Prose never defines rules.

## Validation

`validation/solver.py` searches breadth-first with the engine's own
transition function. The search key drops only bookkeeping that no condition
can read (what was seen or inspected, the state of empty decorative
containers), and skips actions the engine defines as no-ops on that key, so
the reduction is sound and BFS proves minimum lengths. With the whole space
explored, a reverse search proves that the goal stays reachable from every
reachable state: nothing required is missable or destroyable.

## Data and roles

Two Postgres roles, created by the first migration:

* `escapement_api` serves reads and owner-scoped writes. It has no privilege
  on `sealed_manifests`, `run_states`, `jobs`, `rate_counters` or
  `reference_cache`.
* `escapement_service` is used by the gateway's trusted services.

Every user-owned table has row-level security keyed on
`current_setting('app.user_id')`, which the app sets per transaction. The
`transitions` policy implements the replay embargo at the database level. On
SQLite (zero-setup local mode and tests) the same service-layer checks apply.

## Web

Client components fetch with SWR through the same-origin proxy. Every write
carries `X-Escapement-Client: web`; cookie-authenticated writes without it are
rejected, which doubles as CSRF protection. The certificate page renders its
metadata server-side so shared links unfurl.
