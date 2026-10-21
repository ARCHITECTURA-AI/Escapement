# Operations

## Modes

* `ESCAPEMENT_MODE=local` (default): self-hosted research mode. One-click
  local sign-in, admin endpoints and the Lab pages are on, an embedded worker
  runs jobs, and the signing key is generated into the data directory.
* `ESCAPEMENT_MODE=public`: the hosted arena. GitHub sign-in only, every
  `/api/v1/admin/*` call is rejected by the backend, and
  `ESCAPEMENT_SIGNING_KEY` must be set.

## Hosting

A managed container host runs three processes from one image
(`docker/backend.Dockerfile`): `escapement-api serve --no-worker`,
`escapement-api worker`, and optionally `escapement-worker` for reference
runs, plus the web image (`docker/web.Dockerfile`, with
`ESCAPEMENT_API_INTERNAL_URL` pointing at the API). Use managed Postgres and
S3-compatible storage (`ESCAPEMENT_REPLAY_STORE=s3`, `ESCAPEMENT_S3_BUCKET`).
Run `escapement-api migrate` before starting a new release.

## Operator commands (public mode)

```bash
escapement-api ops create-season s1 --name "Season One" --starts-at 2026-11-02T00:00:00Z
escapement-api ops close-season s1          # publishes templates, seeds, replays and the report
escapement-api ops revoke cert_... --reason "abuse"
escapement-api ops kill-switch on           # refuses new runs and cancels live ones
escapement-api ops reference-key            # API key for the reference worker
```

Seasons also open and close on schedule through the sweeper, and the close
job ends any live ranked run first so every ending is recorded.

## Keys

Generate a signing key with
`python -c "from escapement_engine.certificate import generate_keypair; print(generate_keypair()[0])"`.
To rotate, deploy the new key; the old public key stays in `signing_keys` (set
`retired`), so old certificates keep verifying.

## Limits (proposed defaults)

All configurable with `ESCAPEMENT_*` environment variables: 50 runs a day per
user (20 for accounts under seven days old), a global daily ceiling, 240
requests a minute per key and 480 per user, 16 KB payloads, ten idle minutes,
thirty minutes of wall time, three certified runs per instance per agent
version, three Daily attempts per board. The methodology page reads the live
values from `/api/v1/meta`.

## Reference worker

Needs `ESCAPEMENT_REFERENCE_KEY`, `ESCAPEMENT_BASE_URL` and, for LLM agents,
`GROQ_API_KEY` and `REFERENCE_MODELS`. Without a provider key it runs only the
free baselines. It persists daily token usage per provider and model, stops
at 90% of the daily limit and defers remaining jobs to the next UTC day.
