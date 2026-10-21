"use client";

import { Check, ClipboardCopy, FileText, Lock } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { endingLabel, interval, pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { VersionResults } from "@/lib/types";
import { Badge, Button, Card, CardHeader, IntervalBar, Notice, Progress, Source } from "./ui";

export type TimelinePoint = { agent_version_id: string; label: string; created_at: string; mode: string | null; tier: string | null; rate: number | null; ci_low: number | null; ci_high: number | null; runs: number };

/** Success rate with its interval for each agent version, in order of creation. */
export function VersionTimeline({ points }: { points: TimelinePoint[] }) {
  const pts = points.filter((p) => p.rate !== null);
  if (pts.length === 0) return <p className="px-5 py-8 text-center text-sm text-muted">Finish runs with an agent version to see it here.</p>;
  const W = 640;
  const H = 220;
  const pad = { l: 44, r: 16, t: 16, b: 44 };
  const x = (i: number) => pad.l + (pts.length === 1 ? (W - pad.l - pad.r) / 2 : (i / (pts.length - 1)) * (W - pad.l - pad.r));
  const y = (v: number) => pad.t + (1 - v) * (H - pad.t - pad.b);
  return (
    <div className="overflow-x-auto px-3 pb-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[480px]" role="img" aria-label="Success rate by agent version, with 95% intervals">
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeDasharray={v === 0 ? undefined : "3 4"} />
            <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--faint)">{v * 100}%</text>
          </g>
        ))}
        {pts.length > 1 && <polyline fill="none" stroke="var(--signal)" strokeWidth="1.5" strokeOpacity="0.5" points={pts.map((p, i) => `${x(i)},${y(p.rate!)}`).join(" ")} />}
        {pts.map((p, i) => (
          <g key={p.agent_version_id}>
            <title>{`${p.label}: ${pct(p.rate)} (95% interval ${interval(p.ci_low, p.ci_high)}), ${p.runs} runs, ${p.mode} ${p.tier}`}</title>
            <line x1={x(i)} x2={x(i)} y1={y(p.ci_low!)} y2={y(p.ci_high!)} stroke="var(--signal)" strokeWidth="2" />
            <line x1={x(i) - 5} x2={x(i) + 5} y1={y(p.ci_low!)} y2={y(p.ci_low!)} stroke="var(--signal)" strokeWidth="2" />
            <line x1={x(i) - 5} x2={x(i) + 5} y1={y(p.ci_high!)} y2={y(p.ci_high!)} stroke="var(--signal)" strokeWidth="2" />
            <circle cx={x(i)} cy={y(p.rate!)} r="5" fill="var(--surface)" stroke="var(--signal)" strokeWidth="2.5" />
            <text x={x(i)} y={H - pad.b + 18} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{p.label.length > 18 ? `${p.label.slice(0, 17)}…` : p.label}</text>
            <text x={x(i)} y={H - pad.b + 32} textAnchor="middle" fontSize="10" fill="var(--faint)">{p.runs} runs · {p.tier}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export function ResultsTable({ results }: { results: VersionResults["results"] }) {
  if (!results.length) return <p className="px-5 py-5 text-sm text-muted">No finished runs yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-sunken text-left text-[13px] text-muted">
          <tr>
            <th className="px-5 py-2.5 font-medium">Where</th>
            <th className="px-5 py-2.5 font-medium">Success · 95% interval</th>
            <th className="px-5 py-2.5 text-right font-medium">Escapes / runs</th>
            <th className="px-5 py-2.5 text-right font-medium">Rooms</th>
            <th className="px-5 py-2.5 text-right font-medium">pass^3</th>
            <th className="px-5 py-2.5 text-right font-medium">Median actions</th>
            <th className="px-5 py-2.5 text-right font-medium">Cost / run</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {results.map((g, i) => (
            <tr key={i}>
              <td className="px-5 py-3">
                <div className="font-medium capitalize text-ink">{g.mode}{g.season_id ? ` · ${g.season_id}` : ""}</div>
                <div className="text-xs capitalize text-muted">{g.tier} tier</div>
              </td>
              <td className="w-64 px-5 py-3">
                <div className="flex justify-between text-[13px]"><span className="font-semibold tabular text-ink">{pct(g.summary.rate)}</span><span className="tabular text-muted">{interval(g.summary.ci_low, g.summary.ci_high)}</span></div>
                <IntervalBar className="mt-1.5" rate={g.summary.rate} lo={g.summary.ci_low} hi={g.summary.ci_high} />
              </td>
              <td className="px-5 py-3 text-right font-mono tabular">{g.summary.escapes}/{g.summary.runs}</td>
              <td className="px-5 py-3 text-right font-mono tabular">{g.summary.instances}</td>
              <td className="px-5 py-3 text-right font-mono tabular">{pct(g.summary.pass3)}</td>
              <td className="px-5 py-3 text-right font-mono tabular">{g.summary.median_actions_success ?? "—"}</td>
              <td className="px-5 py-3 text-right">
                <span className="font-mono tabular">{g.cost.median_cost_usd != null ? `$${g.cost.median_cost_usd.toFixed(4)}` : "—"}</span>
                {g.cost.median_cost_usd != null && <div className="text-[11px] text-self">self-reported</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Endings({ endings }: { endings: Record<string, number> }) {
  const total = Object.values(endings).reduce((a, b) => a + b, 0);
  if (!total) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(endings).map(([k, v]) => (
        <Badge key={k} tone={k === "escaped" ? "good" : k === "in_progress" ? "signal" : "neutral"}>{endingLabel(k)} · {v}</Badge>
      ))}
    </div>
  );
}

type Bullet =
  | { available: true; text: string; measured_part: string; self_reported_part: string[]; note: string; floor: string; season_id: string; tier: string }
  | { available: false; reason: string; progress: { eligible_instances: number; needed_instances: number; season_id: string | null; tier: string | null } };

export function ResumeBullet({ versionId }: { versionId: string }) {
  const { data } = useApi<Bullet>(`/api/v1/agents/${versionId}/bullet`);
  const [copied, setCopied] = useState(false);
  if (!data) return null;
  return (
    <Card>
      <CardHeader title="Resume bullet" icon={<FileText className="size-4" aria-hidden />} subtitle="Generated from server-measured numbers only; self-reported numbers are labelled" />
      <div className="p-5">
        {data.available ? (
          <>
            <blockquote className="rounded-xl border border-line bg-sunken px-4 py-3 font-serif text-[1.08rem] leading-relaxed text-ink">{data.text}</blockquote>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="primary"
                onClick={async () => {
                  await navigator.clipboard.writeText(data.text);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }}
                icon={copied ? <Check className="size-4" aria-hidden /> : <ClipboardCopy className="size-4" aria-hidden />}
              >
                {copied ? "Copied" : "Copy bullet"}
              </Button>
              <Source kind="server" />
              {data.self_reported_part.length > 0 && <Source kind="self" />}
            </div>
            <p className="mt-3 text-xs text-muted">{data.note} Link your profile next to it so a reviewer can check every number.</p>
          </>
        ) : (
          <div>
            <Notice icon={<Lock className="size-4" aria-hidden />} title="Not enough evidence yet">{data.reason}</Notice>
            <div className="mt-4">
              <div className="mb-1.5 flex justify-between text-sm"><span className="text-muted">Rooms with three certified runs</span><span className="font-mono tabular text-ink">{data.progress.eligible_instances} / {data.progress.needed_instances}</span></div>
              <Progress value={data.progress.eligible_instances} max={data.progress.needed_instances} label="Bullet progress" />
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

export function VersionCard({ v, owner }: { v: VersionResults; owner?: boolean }) {
  const a = v.agent_version;
  const ref = a.agent_type === "reference";
  return (
    <Card>
      <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Link href={`/agents/${a.id}`} className="font-serif text-2xl text-ink hover:underline">{a.name} <span className="text-muted">{a.version}</span></Link>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
            {a.model && <span>{a.model}</span>}
            {a.model && <Source kind={ref ? "attested" : "self"} />}
            {a.framework && <span className="text-muted">· {a.framework}</span>}
            {a.memory && <span className="text-muted">· memory: {a.memory}</span>}
          </div>
        </div>
        <div className="text-right text-sm text-muted">
          <div>{v.total_runs} runs</div>
          <Endings endings={v.endings} />
        </div>
      </div>
      <ResultsTable results={v.results} />
      {owner && a.notes && <p className="border-t border-line px-5 py-3 text-sm text-ink-2">{a.notes}</p>}
    </Card>
  );
}
