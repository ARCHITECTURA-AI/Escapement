"""`escapement`: the command-line tool.

    escapement play                       play Practice in the terminal (local engine)
    escapement login                      save an API key for the hosted arena
    escapement baseline heuristic         run a baseline locally, or --remote for a certified run
    escapement generate --tier standard   generate and validate a room (local research mode)
    escapement validate room.json         run the validation suite on a manifest
    escapement batch --agent heuristic    batch-run a baseline over generated rooms and export results
    escapement verify cert.json           check a certificate offline (add --replay, --manifest)
    escapement replay replay.json         verify and print a replay
    escapement export RUN_ID              download a run's replay and certificate
    escapement mcp                        start the MCP server on stdio
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from escapement_engine import ENGINE_VERSION

from ..sdk.config import config_dir, load_config, resolve, save_config
from ..sdk.tools import describe_observation

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def ok(text: str) -> str:
    return c(text, "32")


def bad(text: str) -> str:
    return c(text, "31")


def dim(text: str) -> str:
    return c(text, "2")


def _read_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except FileNotFoundError:
        sys.exit(f"File not found: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"{path} is not valid JSON: {exc}")


# ----------------------------------------------------------------- play

HELP = """Commands (the same six tools agents use):
  inspect <id>            take <id>            use <item> <target>
  open <id> | close <id>  activate <id>        code <id> <digits>
  move <location>         journal              help | quit
The emergency clock advances when you take an action, not while you read."""


def parse_command(line: str) -> dict[str, Any] | None:
    parts = line.strip().split()
    if not parts:
        return None
    verb, args = parts[0].lower(), parts[1:]
    if verb in ("inspect", "look", "x") and len(args) == 1:
        return {"tool": "inspect", "arguments": {"target_id": args[0]}}
    if verb in ("take", "get") and len(args) == 1:
        return {"tool": "take", "arguments": {"item_id": args[0]}}
    if verb == "use" and len(args) == 2:
        return {"tool": "use", "arguments": {"item_id": args[0], "target_id": args[1]}}
    if verb == "use" and len(args) == 3 and args[1] in ("on", "with"):
        return {"tool": "use", "arguments": {"item_id": args[0], "target_id": args[2]}}
    if verb in ("open", "close", "activate") and len(args) == 1:
        return {"tool": "interact", "arguments": {"target_id": args[0], "operation": verb}}
    if verb in ("code", "enter") and len(args) == 2:
        return {"tool": "interact", "arguments": {"target_id": args[0], "operation": "enter_code", "value": args[1]}}
    if verb in ("move", "go") and len(args) == 1:
        return {"tool": "move", "arguments": {"destination_id": args[0]}}
    if verb in ("journal", "j", "review_journal"):
        return {"tool": "review_journal", "arguments": {}}
    return {"error": f"Not a command: {line.strip()!r}. Type help."}


def cmd_play(args: argparse.Namespace) -> None:
    from ..sdk.local import LocalRun

    run = LocalRun(args.room, tier=args.tier, seed=args.seed)
    print(c(run.room["title"], "1"))
    print(run.room["intro"])
    print(dim(HELP))
    print()
    print(describe_observation(run.observation))
    while not run.done:
        try:
            line = input(c("\n> ", "36"))
        except (EOFError, KeyboardInterrupt):
            print()
            run.finish()
            break
        if line.strip() in ("quit", "exit", "q"):
            run.finish()
            break
        if line.strip() in ("help", "?", "h"):
            print(HELP)
            continue
        cmd = parse_command(line)
        if cmd is None:
            continue
        if "error" in cmd:
            print(bad(cmd["error"]))
            continue
        result = run.send_raw(cmd)
        mark = ok("✓") if result["ok"] else bad(f"✗ {result['error']}")
        print(f"{mark} {result['message']}")
        if result.get("data", {}).get("clues"):
            for clue in result["data"]["clues"]:
                print(f"  {c(clue['id'], '33')}: {clue['text']}")
        print(dim(f"[{run.observation['actions_used']}/{run.observation['action_budget']} actions]"))
        if not run.done:
            print(describe_observation(run.observation).split("\nLast result")[0])
    print()
    print(ok("You escaped!") if run.escaped else bad(f"Run ended: {run.status.replace('_', ' ')}."))
    if args.save:
        Path(args.save).write_text(json.dumps(run.replay(), indent=1))
        print(f"Replay saved to {args.save}. Check it with: escapement replay {args.save}")


# ----------------------------------------------------------------- arena


def cmd_login(args: argparse.Namespace) -> None:
    key = args.key or input("Paste your API key (esk_...): ").strip()
    if not key.startswith("esk_"):
        sys.exit("API keys start with esk_. Create one on the Enter page of the web app.")
    path = save_config(api_key=key, base_url=args.base_url)
    from ..sdk.client import Client

    try:
        meta = Client(api_key=key, base_url=args.base_url).meta()
        print(ok(f"Saved to {path}. Connected to Escapement ({meta['mode']} mode, engine {meta['engine_version']})."))
    except Exception as exc:
        print(f"Saved to {path}, but the server did not answer: {exc}")


def _agent(name: str, args: argparse.Namespace) -> Any:
    from escapement_engine.agents import make_agent

    return make_agent(name, seed=args.seed)


def cmd_baseline(args: argparse.Namespace) -> None:
    agent = _agent(args.agent, args)
    if args.remote:
        from ..sdk.client import Client

        client = Client()
        run = client.create_run(args.room, agent={"name": agent.name, "version": agent.version, "model": "none (rule-based baseline)", "framework": "escapement-engine baselines", "memory": "explicit state"}, replace_active=True)
        print(f"Run {run.id}: {run.watch_url}")
        obs = run.observation
        agent.reset()
        while not run.done:
            req = agent.act(obs)
            result = run.send_raw(req)
            obs = run.observation
            if args.verbose:
                print(f"{run.sequence:>3} {req['tool']} {req.get('arguments', {})} -> {result['message'][:80]}")
        run.finish()
        print(f"Outcome: {run.status} ({run.observation['actions_used']} actions). Certificate: {run.certificate_url}")
        return
    from escapement_engine.agents import run_local
    from escapement_engine.generation import generate, practice_manifest
    from escapement_engine.replay import replay_from_episode

    manifest = practice_manifest() if args.room == "practice" else generate(args.tier, args.room_seed, args.room).manifest
    res = run_local(agent, manifest, f"local-{args.agent}")
    if args.verbose:
        for rec in res.episode.records:
            print(f"{rec.seq:>3} {rec.action.get('tool')} {rec.action.get('arguments', {})} -> {rec.result['message'][:80]}")
    print(f"{args.agent}: {res.outcome} in {res.actions_used} actions; final chain hash {res.final_chain_hash[:16]}…")
    if args.save:
        Path(args.save).write_text(json.dumps(replay_from_episode(res.episode), indent=1))
        print(f"Replay saved to {args.save}")


def cmd_export(args: argparse.Namespace) -> None:
    from ..sdk.client import Client

    client = Client()
    replay = client.replay(args.run_id)
    out = Path(args.out or ".")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.run_id}.replay.json").write_text(json.dumps(replay, indent=1))
    print(f"replay   -> {out / f'{args.run_id}.replay.json'}")
    if replay.get("certificate_id"):
        cert = client.certificate(replay["certificate_id"])
        (out / f"{args.run_id}.certificate.json").write_text(json.dumps(cert, indent=1))
        print(f"certificate -> {out / f'{args.run_id}.certificate.json'}")
    try:
        manifest = client.request("GET", f"/api/v1/rooms/{replay['room']['room_id']}/manifest")
        (out / f"{replay['room']['room_id']}.manifest.json").write_text(json.dumps(manifest, indent=1))
        print(f"manifest -> {out / (replay['room']['room_id'] + '.manifest.json')}")
    except Exception:
        print(dim("manifest is sealed until the room's results are released"))


# ----------------------------------------------------------------- research


def cmd_generate(args: argparse.Namespace) -> None:
    from escapement_engine.generation import generate, manifest_json

    g = generate(args.tier, args.seed, args.room_id or f"{args.tier}-{args.seed}")
    for check in g.report.checks:
        print(f"  {ok('pass') if check.passed else bad('FAIL')}  {check.name}" + (dim(f"  {check.detail}") if check.detail else ""))
    print(f"instance hash {g.instance_hash}")
    print(f"shortest solution {g.min_length} actions ({'proven minimum' if g.optimality == 'proven' else 'best verified'}), budget {g.manifest.budget.actions}")
    if args.out:
        Path(args.out).write_text(manifest_json(g.manifest))
        print(f"manifest -> {args.out}")
    if args.solution:
        Path(args.solution).write_text(json.dumps(g.solution, indent=1))
        print(f"solution -> {args.solution}")


def cmd_validate(args: argparse.Namespace) -> None:
    from escapement_engine.generation import load_manifest
    from escapement_engine.validation import validate

    report = validate(load_manifest(_read_json(args.manifest)))
    for check in report.checks:
        print(f"  {ok('pass') if check.passed else bad('FAIL')}  {check.name}" + (dim(f"  {check.detail}") if check.detail else ""))
    if report.passed:
        print(ok(f"valid: shortest solution {report.min_length} actions ({report.optimality})"))
    else:
        sys.exit(bad("invalid"))


def cmd_batch(args: argparse.Namespace) -> None:
    from escapement_engine.agents import make_agent, run_local
    from escapement_engine.generation import generate
    from escapement_engine.stats import floor_pct, interval_text, summarize

    results: dict[str, list[tuple[bool, int]]] = {}
    rows = []
    for i in range(args.instances):
        g = generate(args.tier, f"{args.seed}-{i}", f"batch-{args.tier}-{i}")
        for r in range(args.runs):
            agent = make_agent(args.agent, seed=f"{args.seed}-{i}-{r}")
            res = run_local(agent, g.manifest, f"batch-{i}-{r}")
            results.setdefault(g.instance_hash, []).append((res.outcome == "escaped", res.actions_used))
            rows.append({"instance": g.manifest.room_id, "instance_hash": g.instance_hash, "run": r, "outcome": res.outcome, "actions_used": res.actions_used, "min_length": g.min_length})
        print(dim(f"instance {i + 1}/{args.instances} done"), end="\r")
    s = summarize(results)
    print()
    print(f"{args.agent} on {args.instances} {args.tier} instances x {args.runs} runs:")
    print(f"  escapes {s.escapes}/{s.runs} = {floor_pct(s.rate)} (95% CI {interval_text(s.ci_low, s.ci_high)}, instance resampling)")
    print(f"  pass^3 {floor_pct(s.pass3)} over {s.pass3_instances} instances; median actions per escape {s.median_actions_success}")
    if args.out:
        Path(args.out).write_text(json.dumps({"agent": args.agent, "tier": args.tier, "summary": s.to_dict(), "runs": rows}, indent=1))
        print(f"results -> {args.out}")


# ----------------------------------------------------------------- verification


def _keyset(args: argparse.Namespace) -> dict[str, Any]:
    if args.keys:
        return _read_json(args.keys)
    cache = config_dir() / "keys.json"
    if not args.offline:
        try:
            from ..sdk.client import Client

            keys = Client(base_url=args.base_url).keys()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(keys))
            return keys
        except Exception as exc:
            if not cache.exists():
                sys.exit(f"Could not fetch the published keys ({exc}). Pass --keys keys.json for offline checks.")
            print(dim("using cached keys"))
    if cache.exists():
        return json.loads(cache.read_text())
    sys.exit("No cached keys. Run once online or pass --keys keys.json.")


def cmd_verify(args: argparse.Namespace) -> None:
    from escapement_engine.certificate import verify
    from escapement_engine.generation import load_manifest

    cert = _read_json(args.certificate)
    replay = _read_json(args.replay) if args.replay else None
    manifest = load_manifest(_read_json(args.manifest)) if args.manifest else None
    report = verify(cert, _keyset(args), replay, manifest)
    levels = {"none": "nothing verified", "signature": "signature", "chain": "signature + hash chain", "full": "signature + hash chain + full re-simulation"}
    print(f"certificate {cert.get('certificate_id')}  run {cert.get('run_id')}")
    print(f"outcome {cert.get('outcome')} in {cert.get('actions_used')}/{cert.get('action_budget')} actions; room {cert.get('room', {}).get('room_id')}")
    for p in report.problems:
        print(bad(f"  ✗ {p}"))
    for n in report.notes:
        print(dim(f"  · {n}"))
    if not args.offline and report.signature_valid:
        try:
            from ..sdk.client import Client

            page = Client(base_url=args.base_url).request("GET", f"/api/v1/certificates/{cert['certificate_id']}")
            if page.get("revoked"):
                print(bad(f"  ✗ revoked: {page.get('revocation_reason')}"))
                sys.exit(1)
            print(dim("  · not revoked (checked online)"))
        except SystemExit:
            raise
        except Exception:
            print(dim("  · revocation status not checked (server unreachable)"))
    agent = cert.get("agent", {})
    print(dim(f"  self-reported: agent {agent.get('name')} {agent.get('version')}, model {agent.get('model')}" if not agent.get("model_attested") else f"  first-party reference run: {agent.get('provider')} {agent.get('model')}"))
    if report.ok:
        print(ok(f"VALID ({levels[report.level]})"))
    else:
        sys.exit(bad("INVALID"))


def cmd_replay(args: argparse.Namespace) -> None:
    from escapement_engine.generation import load_manifest
    from escapement_engine.replay import resimulate, verify_chain

    replay = _read_json(args.replay)
    if "replay" in replay and "steps" not in replay:
        replay = replay["replay"]
    chain = verify_chain(replay)
    print(f"run {replay['run_id']} on {replay['room']['room_id']} ({replay['room'].get('tier')}), outcome {replay['outcome']}")
    print((ok("chain ok") if chain.ok else bad(f"chain BROKEN: {chain.reason} at step {chain.first_bad_seq}")) + dim(f"  ({chain.steps_checked} steps)"))
    if args.manifest:
        sim = resimulate(replay, load_manifest(_read_json(args.manifest)))
        print(ok("re-simulation matches") if sim.ok else bad("re-simulation differs: " + "; ".join(sim.mismatches[:3])))
    if not args.quiet:
        for step in replay["steps"]:
            a = step["action"]
            r = step["result"]
            mark = ok("✓") if r.get("ok") else bad("✗")
            args_text = ", ".join(f"{v}" for v in (a.get("arguments") or {}).values()) if isinstance(a.get("arguments"), dict) else ""
            print(f"{step['seq']:>3} {mark} {a.get('tool')}({args_text}) {dim(r.get('message', '')[:90])}")
            if step.get("decision_summary"):
                print(dim(f"      agent-provided summary: {step['decision_summary']}"))
    if not chain.ok:
        sys.exit(1)


def cmd_mcp(args: argparse.Namespace) -> None:
    from ..mcp.server import main as mcp_main

    mcp_main()


def cmd_version(args: argparse.Namespace) -> None:
    from .. import __version__

    key, url = resolve()
    print(f"escapement {__version__}, engine {ENGINE_VERSION}")
    print(f"server {url}; api key {'configured' if key else 'not set'}; config {config_dir() / 'config.json'}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="escapement", description="Prove what your AI agent can do.")
    parser.add_argument("--base-url", default=None, help="Escapement server (default: config or http://localhost:3000)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("play", help="Play a room in the terminal (local engine)")
    p.add_argument("--room", default="practice", help="practice, or any id to generate a room")
    p.add_argument("--tier", default="standard")
    p.add_argument("--seed", default="local")
    p.add_argument("--save", help="Write the replay to this file")
    p.set_defaults(func=cmd_play)

    p = sub.add_parser("login", help="Save an API key")
    p.add_argument("--key")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("baseline", help="Run the random or heuristic baseline")
    p.add_argument("agent", choices=["random", "heuristic"])
    p.add_argument("--room", default="practice")
    p.add_argument("--tier", default="standard")
    p.add_argument("--room-seed", default="local")
    p.add_argument("--seed", default="0")
    p.add_argument("--remote", action="store_true", help="Play through the API for a certified run")
    p.add_argument("--save")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("generate", help="Generate and validate a room instance")
    p.add_argument("--tier", default="standard", choices=["practice", "standard", "hard"])
    p.add_argument("--seed", required=True)
    p.add_argument("--room-id")
    p.add_argument("--out")
    p.add_argument("--solution")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("validate", help="Run the validation suite on a manifest")
    p.add_argument("manifest")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("batch", help="Batch-run a baseline and export results")
    p.add_argument("--agent", default="heuristic", choices=["random", "heuristic"])
    p.add_argument("--tier", default="standard", choices=["practice", "standard", "hard"])
    p.add_argument("--instances", type=int, default=10)
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--seed", default="batch")
    p.add_argument("--out")
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("verify", help="Verify a certificate offline")
    p.add_argument("certificate")
    p.add_argument("--replay")
    p.add_argument("--manifest")
    p.add_argument("--keys", help="Key set JSON (from /.well-known/escapement-keys.json)")
    p.add_argument("--offline", action="store_true", help="Use cached or given keys only; skip the revocation check")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("replay", help="Verify and print a replay file")
    p.add_argument("replay")
    p.add_argument("--manifest")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("export", help="Download a run's replay, certificate and (if public) manifest")
    p.add_argument("run_id")
    p.add_argument("--out")
    p.set_defaults(func=cmd_export)

    sub.add_parser("mcp", help="Start the MCP server on stdio").set_defaults(func=cmd_mcp)
    sub.add_parser("version", help="Show versions and configuration").set_defaults(func=cmd_version)

    args = parser.parse_args(argv)
    if args.base_url:
        os.environ["ESCAPEMENT_BASE_URL"] = args.base_url
    args.func(args)


if __name__ == "__main__":
    main()
