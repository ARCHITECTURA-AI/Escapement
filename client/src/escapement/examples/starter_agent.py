"""Escapement starter agent: an LLM with tool calls plays the Practice room.

    export ESCAPEMENT_API_KEY=esk_...      # from the web app's Enter page
    export MODEL_API_KEY=gsk_...           # any OpenAI-compatible provider (Groq by default)
    python -m escapement.examples.starter_agent
"""

import json
import os

import httpx

from escapement import SYSTEM_PROMPT, Client, describe_observation, openai_tools

BASE = os.environ.get("MODEL_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.environ.get("MODEL", "openai/gpt-oss-20b")
ROOM = os.environ.get("ESCAPEMENT_ROOM", "practice")


def chat(messages):
    resp = httpx.post(
        f"{BASE}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"},
        json={"model": MODEL, "messages": messages, "tools": openai_tools(), "tool_choice": "required"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    client = Client()
    run = client.create_run(ROOM, agent={"name": "starter-agent", "version": "1.0.0", "model": MODEL, "framework": "escapement starter", "memory": "full transcript"})
    print(f"Run {run.id} started. Watch it live: {run.watch_url}")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": run.room["intro"] + "\n\n" + describe_observation(run.observation)}]
    while not run.done:
        reply = chat(messages)
        msg = reply["choices"][0]["message"]
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
        usage = {"tokens_in": reply["usage"]["prompt_tokens"], "tokens_out": reply["usage"]["completion_tokens"], "model_decisions": 1}
        for call in msg.get("tool_calls") or []:
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = call["function"]["arguments"]  # sent as-is: the server records malformed calls
            result = run.send_raw({"tool": call["function"]["name"], "arguments": args, "decision_summary": msg.get("content"), "usage": usage})
            usage = None
            print(f"{run.sequence:>3} {call['function']['name']}({args}) -> {result['message']}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": describe_observation(run.observation)})
            if run.done:
                break
        if len(messages) > 40:  # keep the context small: system, intro, recent turns
            messages = messages[:2] + messages[-20:]
            while messages[2]["role"] == "tool":
                messages.pop(2)
    run.finish()
    print(f"Outcome: {run.status} in {run.observation['actions_used']} actions.")
    print(f"Certificate: {run.certificate_url}")


if __name__ == "__main__":
    main()
