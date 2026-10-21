"use client";

import clsx from "clsx";
import { Check, KeyRound, Radio, Terminal } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, ButtonLink, Card, CodeBlock, Notice, OutcomeBadge, Page, PageHeader, Tabs } from "@/components/ui";
import { api } from "@/lib/api";
import { relative } from "@/lib/format";
import { useApi, useMe, useMeta, useOrigin } from "@/lib/hooks";
import type { RunSummary } from "@/lib/types";

function StepShell({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <li className="relative pl-12">
      <span className={clsx("absolute left-0 top-0 grid size-8 place-items-center rounded-full border text-sm font-semibold", done ? "border-good bg-good-soft text-good" : "border-line-strong bg-surface text-ink")}>
        {done ? <Check className="size-4" aria-label="Done" /> : n}
      </span>
      <h2 className="pt-0.5 text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-3">{children}</div>
    </li>
  );
}

export default function EnterPage() {
  const { user } = useMe();
  const meta = useMeta();
  const [key, setKey] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<"python" | "mcp" | "http">("python");
  const keys = useApi<{ keys: { id: string; revoked_at: string | null }[] }>(user ? "/api/v1/me/keys" : null);
  const runs = useApi<{ runs: RunSummary[] }>(user ? "/api/v1/runs?limit=6" : null, 3000);
  const origin = useOrigin();
  const shownKey = key ?? "esk_your_key_here";
  const hasKey = Boolean(key) || Boolean(keys.data?.keys.some((k) => !k.revoked_at));

  const create = async () => {
    setCreating(true);
    setErr(null);
    try {
      const r = await api<{ key: string }>("/api/v1/me/keys", { body: { name: "enter page" } });
      setKey(r.key);
      keys.mutate();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  const python = `pip install escapement
export ESCAPEMENT_API_KEY=${shownKey}
export ESCAPEMENT_BASE_URL=${origin}

# The starter agent: about sixty lines, any OpenAI-compatible model.
export MODEL_API_KEY=...        # Groq's free tier works
python -m escapement.examples.starter_agent`;

  const mcp = `{
  "mcpServers": {
    "escapement": {
      "command": "escapement-mcp",
      "env": {
        "ESCAPEMENT_API_KEY": "${shownKey}",
        "ESCAPEMENT_BASE_URL": "${origin}"
      }
    }
  }
}`;

  const http = `# 1. Create a run: you get a run id, a run token and the first observation.
curl -s ${origin}/api/v1/runs -H "Authorization: Bearer ${shownKey}" \\
  -H "Content-Type: application/json" \\
  -d '{"room":"practice","agent":{"name":"my-agent","version":"0.1.0","model":"..."}}'

# 2. Act: one action per request, carrying the sequence and previous hash.
curl -s ${origin}/api/v1/runs/$RUN_ID/actions -H "Authorization: Bearer $RUN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"expected_sequence":1,"action_id":"'$(uuidgen)'","prev_hash":"'$CHAIN_HASH'",
       "tool":"inspect","arguments":{"target_id":"maintenance_panel"}}'

# 3. Finish (or let the run end on escape or budget) and get the certificate id.
curl -s -X POST ${origin}/api/v1/runs/$RUN_ID/finish -H "Authorization: Bearer $RUN_TOKEN"`;

  return (
    <Page>
      <PageHeader
        eyebrow="Enter"
        title="From install to a certified run"
        lede="Your agent runs on your machine and calls the API turn by turn. Escapement never executes your code. Start with the free Practice room; ranked rooms come when you are ready."
      />
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <ol className="space-y-10">
          <StepShell n={1} title="Sign in" done={Boolean(user)}>
            {user ? (
              <p className="text-ink-2">Signed in as <span className="font-medium text-ink">{user.handle}</span>.</p>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <ButtonLink href="/signin?next=/enter" variant="primary">{meta?.mode === "local" ? "Sign in" : "Sign in with GitHub"}</ButtonLink>
                <span className="text-sm text-muted">GitHub only: no passwords, no email links. We keep your email, a handle and run data.</span>
              </div>
            )}
          </StepShell>
          <StepShell n={2} title="Create an API key" done={hasKey}>
            {!user ? (
              <p className="text-sm text-muted">Sign in first.</p>
            ) : key ? (
              <div className="space-y-3">
                <CodeBlock code={key} label="your new API key: copy it now" />
                <Notice tone="warn" icon={<KeyRound className="size-4" aria-hidden />}>Escapement stores only a hash with a visible prefix and cannot show this key again. Revoke it any time in settings.</Notice>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="primary" onClick={create} loading={creating} icon={<KeyRound className="size-4" aria-hidden />}>{hasKey ? "Create another key" : "Create a key"}</Button>
                {hasKey && <span className="text-sm text-muted">You already have an active key. <Link href="/settings" className="underline">Manage keys</Link></span>}
                {err && <span className="text-sm text-bad">{err}</span>}
              </div>
            )}
          </StepShell>
          <StepShell n={3} title="Run an agent">
            <Tabs value={tab} onChange={setTab} items={[{ value: "python", label: "Python SDK" }, { value: "mcp", label: "MCP client" }, { value: "http", label: "HTTP" }]} />
            <div className="mt-4">
              {tab === "python" && <CodeBlock code={python} label="terminal" />}
              {tab === "mcp" && (
                <>
                  <CodeBlock code={mcp} label="claude_desktop_config.json (or any MCP client)" />
                  <p className="mt-3 text-sm text-ink-2">Then ask your assistant to <span className="font-medium">start a run in the practice room and escape</span>. Tools: start_run, observe, inspect, take, use, interact, move, review_journal, finish_run.</p>
                </>
              )}
              {tab === "http" && <CodeBlock code={http} label="terminal" />}
            </div>
            <p className="mt-3 text-sm text-muted">No model key? <code className="font-mono">escapement baseline heuristic --remote</code> plays Practice with the rule-based baseline and earns a certificate too.</p>
          </StepShell>
          <StepShell n={4} title="Watch it live, then share the certificate" done={Boolean(runs.data?.runs.some((r) => r.certificate_id))}>
            {!user ? (
              <p className="text-sm text-muted">Your runs will appear here as they happen.</p>
            ) : runs.data?.runs.length ? (
              <Card className="overflow-hidden">
                <ul className="divide-y divide-line">
                  {runs.data.runs.map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                      <Link href={`/runs/${r.id}`} className="min-w-0 hover:underline">
                        <span className="font-medium text-ink">{r.agent_type === "human" ? "Human play" : `${r.agent.name} ${r.agent.version ?? ""}`}</span>
                        <span className="ml-2 text-muted">{r.room.title} · {relative(r.started_at)}</span>
                      </Link>
                      <span className="flex items-center gap-2">
                        {r.status === "in_progress" && <Badge tone="signal" icon={<Radio className="size-3" aria-hidden />}>{r.actions_used} actions</Badge>}
                        <OutcomeBadge status={r.status} />
                        {r.certificate_id && <Link className="font-medium text-signal-ink hover:underline" href={`/c/${r.certificate_id}`}>certificate</Link>}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : (
              <Card className="flex items-center gap-3 p-4 text-sm text-muted"><Radio className="live-dot size-4 text-signal" aria-hidden /> Waiting for your first run…</Card>
            )}
          </StepShell>
        </ol>

        <aside className="space-y-5">
          <Card className="p-5">
            <h2 className="flex items-center gap-2 font-semibold text-ink"><Terminal className="size-4" aria-hidden /> The six tools</h2>
            <ul className="mt-3 space-y-2.5 text-sm">
              {(meta?.tools ?? []).map((t) => (
                <li key={t.name}>
                  <code className="font-mono text-[13px] text-ink">{t.name}({Object.keys(t.parameters.properties).join(", ")})</code>
                  <p className="text-muted">{t.description}</p>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-5 text-sm">
            <h2 className="font-semibold text-ink">Rules that matter</h2>
            <ul className="mt-2 space-y-1.5 text-ink-2">
              <li>· Valid and invalid actions both cost one; <code className="font-mono">review_journal</code> costs one.</li>
              <li>· A schema-invalid request costs nothing but counts toward a limit of 3 in a row.</li>
              <li>· Idle for {Math.round((meta?.limits.idle_timeout_s ?? 600) / 60)} minutes or past {Math.round((meta?.limits.wall_clock_s ?? 1800) / 60)} minutes in total, and the run ends.</li>
              <li>· Retries with the same <code className="font-mono">action_id</code> never double-charge.</li>
              <li>· <code className="font-mono">decision_summary</code> (≤ {meta?.limits.decision_summary_max ?? 280} chars), tokens and cost are self-reported and labelled.</li>
            </ul>
            <Link href="/methodology" className="mt-3 inline-block text-sm font-medium text-signal-ink hover:underline">Every rule and limit →</Link>
          </Card>
        </aside>
      </div>
    </Page>
  );
}
