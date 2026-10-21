"""Populate a local Escapement with demo data: players, agent versions, runs,
a season with leaderboards, and a Daily Room attempt.

    escapement-api serve &            # local mode
    python scripts/seed_demo.py --base-url http://localhost:8000

Local research mode only. The "demo-planner" agents read solutions through
the local admin API, which the public arena rejects; they exist to fill the
screens with realistic shapes of data and are labelled as such.
"""

from __future__ import annotations

import argparse
import random
import time

import httpx
from escapement import Client
from escapement_engine.agents import HeuristicExplorer, RandomAgent

WEB = {"X-Escapement-Client": "web"}


def login(base: str, handle: str, public: bool = True) -> tuple[httpx.Client, str]:
    web = httpx.Client(base_url=base, timeout=60)
    web.post("/api/v1/auth/local", json={"handle": handle}).raise_for_status()
    web.patch("/api/v1/me", json={"profile_public": public}, headers=WEB).raise_for_status()
    key = web.post("/api/v1/me/keys", json={"name": "demo"}, headers=WEB).json()["key"]
    return web, key


def play_baseline(client: Client, agent, room: str, meta: dict) -> str:
    run = client.create_run(room, agent=meta, replace_active=True)
    agent.reset()
    while not run.done:
        run.send_raw(agent.act(run.observation))
    run.finish()
    return run.status


def play_planner(client: Client, web: httpx.Client, room: str, meta: dict, skill: float, rng: random.Random) -> str:
    solution = web.get(f"/api/v1/admin/instances/{room}/manifest").json()["solution"]
    run = client.create_run(room, agent=meta, replace_active=True)
    noise = HeuristicExplorer()
    for i, action in enumerate(solution):
        if run.done:
            break
        while rng.random() > skill and not run.done:  # wander
            run.send_raw(noise.act(run.observation))
        if run.done:
            break
        if rng.random() > skill + 0.25 and i > len(solution) // 2:
            break  # gives up mid-run
        run.act(
            action["tool"],
            **action["arguments"],
            decision_summary=f"Step {i + 1}: following my plan.",
            usage={"tokens_in": 900 + rng.randint(0, 300), "tokens_out": 40 + rng.randint(0, 30), "cost_usd": 0.0004},
        )
    run.finish(usage={"model_decisions": run.sequence})
    return run.status


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--instances", type=int, default=5)
    args = ap.parse_args()
    base = args.base_url
    rng = random.Random(7)

    ada_web, ada_key = login(base, "ada")
    grace_web, grace_key = login(base, "grace")
    alan_web, alan_key = login(base, "alan", public=False)
    ada, grace, alan = (Client(api_key=k, base_url=base) for k in (ada_key, grace_key, alan_key))

    print("practice runs")
    for _ in range(2):
        print(
            " heuristic",
            play_baseline(
                ada, HeuristicExplorer(), "practice", {"name": "explorer", "version": "0.1.0", "model": "none", "framework": "rule-based"}
            ),
        )
        print(
            " random",
            play_baseline(
                grace,
                RandomAgent(seed=rng.randint(0, 999)),
                "practice",
                {"name": "dice", "version": "0.1.0", "model": "none", "framework": "random"},
            ),
        )

    print("season")
    r = ada_web.post("/api/v1/admin/seasons", json={"id": "s1", "name": "Season One", "instances": args.instances})
    if r.status_code == 202:
        job = r.json()["job"]["id"]
        while True:
            jobs = {j["id"]: j for j in ada_web.get("/api/v1/admin/jobs").json()["jobs"]}
            if jobs[job]["status"] in ("done", "failed"):
                print(" generation", jobs[job]["status"], jobs[job].get("error") or "")
                break
            time.sleep(1)
    season = ada.request("GET", "/api/v1/seasons/s1")
    rooms = [i["id"] for i in season["instances"]]
    for room in rooms:
        for k in range(3):
            print(
                " ",
                room,
                "ada v1",
                play_planner(
                    ada,
                    ada_web,
                    room,
                    {
                        "name": "planner",
                        "version": "1.0.0",
                        "model": "gpt-oss-120b",
                        "framework": "custom loop",
                        "memory": "structured notebook",
                    },
                    0.9,
                    rng,
                ),
            )
            print(
                " ",
                room,
                "ada v0.9",
                play_planner(
                    ada,
                    ada_web,
                    room,
                    {"name": "planner", "version": "0.9.0", "model": "gpt-oss-20b", "framework": "custom loop", "memory": "transcript"},
                    0.7,
                    rng,
                ),
            )
            print(
                " ",
                room,
                "grace",
                play_planner(
                    grace,
                    ada_web,
                    room,
                    {"name": "scout", "version": "2.1", "model": "qwen3-32b", "framework": "langgraph", "memory": "rolling summary"},
                    0.8,
                    rng,
                ),
            )
            if k == 0:
                print(
                    " ",
                    room,
                    "alan",
                    play_baseline(alan, HeuristicExplorer(), room, {"name": "baseline-copy", "version": "0.0.1", "model": "none"}),
                )
    print("done:", base)


if __name__ == "__main__":
    main()
