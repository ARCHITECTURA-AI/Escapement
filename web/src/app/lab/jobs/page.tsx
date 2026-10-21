"use client";

import { FlaskConical, OctagonX, Play } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, CardHeader, Notice, Page, PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { pct, relative } from "@/lib/format";
import { useApi } from "@/lib/hooks";

type Job = { id: string; kind: string; payload: Record<string, unknown>; status: string; attempts: number; result: Record<string, unknown> | null; error: string | null; progress: string | null; created_at: string; updated_at: string };
type Overview = { users: number; runs: number; live_runs: number; instances: Record<string, number>; jobs: Record<string, number>; kill_switch: boolean; open_reports: number };

const TONE: Record<string, "good" | "bad" | "signal" | "neutral" | "warn"> = { done: "good", failed: "bad", running: "signal", queued: "neutral", cancelled: "warn" };

export default function LabJobs() {
  const jobs = useApi<{ jobs: Job[] }>("/api/v1/admin/jobs", 2000);
  const ov = useApi<Overview>("/api/v1/admin/overview", 4000);
  const [agent, setAgent] = useState("heuristic");
  const [tier, setTier] = useState("standard");
  const [runs, setRuns] = useState(3);
  const [sid, setSid] = useState("s1");
  const [instances, setInstances] = useState(10);
  const [msg, setMsg] = useState<string | null>(null);
  const post = async (path: string, body: unknown) => {
    setMsg(null);
    try {
      await api(path, { body });
      jobs.mutate();
      ov.mutate();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <Page wide>
      <PageHeader eyebrow={<span className="inline-flex items-center gap-2"><FlaskConical className="size-4" aria-hidden /> Local research mode</span>} title="Jobs" lede="Batch runs, season generation and closing, and reference baselines, on the Postgres-backed jobs table. In public mode every one of these calls is rejected by the backend." />
      {msg && <Notice tone="bad" className="mb-5">{msg}</Notice>}
      {ov.data && (
        <div className="mb-6 grid grid-cols-2 gap-6 rounded-2xl border border-line bg-surface p-6 sm:grid-cols-5">
          <Stat label="Users" value={ov.data.users} />
          <Stat label="Runs" value={ov.data.runs} />
          <Stat label="Live runs" value={ov.data.live_runs} />
          <Stat label="Queued jobs" value={ov.data.jobs.queued ?? 0} />
          <div>
            <div className="text-[13px] text-muted">Kill switch</div>
            <Button className="mt-2" size="sm" variant={ov.data.kill_switch ? "danger" : "secondary"} icon={<OctagonX className="size-4" aria-hidden />} onClick={() => post("/api/v1/admin/kill-switch", { on: !ov.data!.kill_switch })}>
              {ov.data.kill_switch ? "On: arena paused" : "Off"}
            </Button>
          </div>
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="space-y-5">
          <Card className="p-5">
            <h2 className="font-semibold text-ink">Batch-run a baseline</h2>
            <p className="mt-1 text-sm text-muted">In-process, unranked, exported as JSON.</p>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <label><span className="text-muted">Agent</span><select value={agent} onChange={(e) => setAgent(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-line-strong bg-surface px-2 text-ink"><option>heuristic</option><option>random</option></select></label>
              <label><span className="text-muted">Tier</span><select value={tier} onChange={(e) => setTier(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-line-strong bg-surface px-2 text-ink"><option>practice</option><option>standard</option><option>hard</option></select></label>
              <label><span className="text-muted">Runs per room</span><input type="number" min={1} max={10} value={runs} onChange={(e) => setRuns(Number(e.target.value))} className="mt-1 h-9 w-full rounded-lg border border-line-strong bg-surface px-2 text-ink" /></label>
            </div>
            <Button className="mt-4" variant="primary" icon={<Play className="size-4" aria-hidden />} onClick={() => post("/api/v1/admin/jobs", { kind: "batch_run", payload: { agent, tier, runs, count: 5 } })}>Queue batch</Button>
          </Card>
          <Card className="p-5">
            <h2 className="font-semibold text-ink">Seasons</h2>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <label><span className="text-muted">Season id</span><input value={sid} onChange={(e) => setSid(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-line-strong bg-surface px-2 font-mono text-ink" /></label>
              <label><span className="text-muted">Rooms per tier</span><input type="number" min={1} max={20} value={instances} onChange={(e) => setInstances(Number(e.target.value))} className="mt-1 h-9 w-full rounded-lg border border-line-strong bg-surface px-2 text-ink" /></label>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => post("/api/v1/admin/seasons", { id: sid, name: `Season ${sid.toUpperCase()}`, instances })}>Generate and open</Button>
              <Button onClick={() => post(`/api/v1/admin/seasons/${sid}/close`, {})}>Close and publish</Button>
            </div>
          </Card>
        </div>
        <Card>
          <CardHeader title="Recent jobs" subtitle="Refreshes every two seconds" />
          <ul className="divide-y divide-line">
            {jobs.data?.jobs.map((j) => {
              const summary = (j.result?.summary ?? null) as { runs: number; escapes: number; rate: number } | null;
              return (
                <li key={j.id} className="px-5 py-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="flex items-center gap-2"><code className="font-mono text-[13px] text-ink">{j.kind}</code><Badge tone={TONE[j.status] ?? "neutral"}>{j.status}</Badge>{j.progress && <span className="text-xs text-muted">{j.progress}</span>}</span>
                    <span className="flex items-center gap-2 text-xs text-muted">
                      {relative(j.updated_at)}
                      {(j.status === "queued" || j.status === "running") && <Button size="sm" variant="ghost" onClick={() => post(`/api/v1/admin/jobs/${j.id}/cancel`, {})}>Cancel</Button>}
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-[11.5px] text-faint">{JSON.stringify(j.payload)}</div>
                  {summary && <div className="mt-1 text-ink-2">{summary.escapes}/{summary.runs} escaped ({pct(summary.rate)})</div>}
                  {j.error && <div className="mt-1 text-xs text-bad">{j.error}</div>}
                </li>
              );
            })}
            {jobs.data?.jobs.length === 0 && <li className="px-5 py-6 text-sm text-muted">No jobs yet.</li>}
          </ul>
        </Card>
      </div>
    </Page>
  );
}
