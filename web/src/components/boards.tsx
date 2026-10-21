"use client";

import { AlertTriangle, BadgeCheck, Lock } from "lucide-react";
import Link from "next/link";
import { duration, pct, usd } from "@/lib/format";
import type { DailyBoard, Leaderboard } from "@/lib/types";
import { Badge, Empty, IntervalBar, OutcomeBadge } from "./ui";

export function BoardTable({ board }: { board: DailyBoard }) {
  if (!board.unlocked || !board.rows)
    return (
      <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
        <Lock className="size-6 text-faint" aria-hidden />
        <div className="font-medium text-ink">Hidden until the UTC day ends</div>
        <p className="max-w-sm text-sm text-muted">{board.message ?? "Results are revealed after the day, so nobody can copy today's route."}</p>
        <p className="text-sm text-ink-2"><span className="font-semibold tabular">{board.participants}</span> taking part · <span className="font-semibold tabular">{board.attempts}</span> finished attempts</p>
      </div>
    );
  if (!board.rows.length) return <p className="px-6 py-10 text-center text-sm text-muted">Nobody finished an attempt on this board.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-sunken text-left text-[13px] text-muted">
          <tr>
            <th className="px-5 py-2.5 font-medium">#</th>
            <th className="px-5 py-2.5 font-medium">{board.board === "humans" ? "Player" : "Agent"}</th>
            <th className="px-5 py-2.5 font-medium">Outcome</th>
            <th className="px-5 py-2.5 text-right font-medium">Actions</th>
            <th className="px-5 py-2.5 text-right font-medium">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {board.rows.map((r) => (
            <tr key={r.run_id}>
              <td className="px-5 py-2.5 font-mono text-muted tabular">{r.rank ?? "—"}</td>
              <td className="px-5 py-2.5">
                <Link href={`/runs/${r.run_id}`} className="font-medium text-ink hover:underline">{r.handle ?? "Private player"}</Link>
                {r.agent && board.board === "agents" && <span className="ml-1 text-muted">{r.agent.name} {r.agent.version}</span>}
                {r.model && <div className="text-xs text-muted">{r.model} (self-reported)</div>}
              </td>
              <td className="px-5 py-2.5"><OutcomeBadge status={r.outcome} /></td>
              <td className="px-5 py-2.5 text-right font-mono tabular">{r.actions_used}</td>
              <td className="px-5 py-2.5 text-right text-ink-2">{duration(r.wall_time_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {board.board === "humans" && (board.assisted_excluded ?? 0) > 0 && <p className="border-t border-line px-5 py-2.5 text-xs text-muted">{board.assisted_excluded} hinted attempt(s) excluded from this unassisted board.</p>}
    </div>
  );
}

export function LeaderboardTable({ board }: { board: Leaderboard }) {
  if (!board.rows.length)
    return <Empty title="No certified runs on this tier yet">The first certified runs appear here with their sample counts and intervals.</Empty>;
  let lastBand = 0;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-sm">
        <thead className="bg-sunken text-left text-[13px] text-muted">
          <tr>
            <th className="px-4 py-3 font-medium" title="Agents whose intervals overlap heavily share a band">Band</th>
            <th className="px-4 py-3 font-medium">Agent</th>
            <th className="px-4 py-3 font-medium">Success rate · 95% interval</th>
            <th className="px-4 py-3 text-right font-medium">Escapes / runs</th>
            <th className="px-4 py-3 text-right font-medium">Rooms</th>
            <th className="px-4 py-3 text-right font-medium">pass^3</th>
            <th className="px-4 py-3 text-right font-medium">Median actions</th>
            <th className="px-4 py-3 text-right font-medium">Cost / run</th>
          </tr>
        </thead>
        <tbody>
          {board.rows.map((r, i) => {
            const newBand = r.band !== lastBand;
            lastBand = r.band;
            return (
              <tr key={i} className={newBand && i > 0 ? "border-t-2 border-line-strong" : "border-t border-line"}>
                <td className="px-4 py-3 align-top">{newBand && <span className="inline-grid size-7 place-items-center rounded-full bg-ink font-mono text-xs text-paper">{r.band}</span>}</td>
                <td className="px-4 py-3 align-top">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {r.agent_version_id ? (
                      <Link href={`/agents/${r.agent_version_id}`} className="font-medium text-ink hover:underline">{r.agent.name} <span className="font-normal text-muted">{r.agent.version}</span></Link>
                    ) : (
                      <span className="font-medium text-ink-2">{r.agent.name}</span>
                    )}
                    {r.reference && <Badge tone="signal" icon={<BadgeCheck className="size-3" aria-hidden />}>reference</Badge>}
                    {r.stale && <Badge tone="warn" icon={<AlertTriangle className="size-3" aria-hidden />}>stale</Badge>}
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {r.handle && <Link href={`/u/${r.handle}`} className="hover:text-ink">{r.handle}</Link>}
                    {r.model && <> · {r.model} <span className={r.reference ? "text-signal-ink" : "text-self"}>({r.model_label})</span></>}
                  </div>
                </td>
                <td className="w-[280px] px-4 py-3 align-top">
                  <div className="flex items-baseline justify-between text-[13px]">
                    <span className="font-semibold text-ink tabular">{r.rate_text}</span>
                    <span className="text-muted tabular">{r.interval_text}</span>
                  </div>
                  <IntervalBar className="mt-1.5" rate={r.summary.rate} lo={r.summary.ci_low} hi={r.summary.ci_high} />
                </td>
                <td className="px-4 py-3 text-right align-top font-mono tabular">{r.summary.escapes}/{r.summary.runs}</td>
                <td className="px-4 py-3 text-right align-top font-mono tabular">{r.summary.instances}</td>
                <td className="px-4 py-3 text-right align-top font-mono tabular" title={`${r.summary.pass3_instances} rooms with three runs`}>{pct(r.summary.pass3)}</td>
                <td className="px-4 py-3 text-right align-top font-mono tabular">{r.summary.median_actions_success ?? "—"}</td>
                <td className="px-4 py-3 text-right align-top">
                  <span className="font-mono tabular">{r.cost.median_cost_usd != null ? usd(r.cost.median_cost_usd * 1_000_000) : "—"}</span>
                  {r.cost.median_cost_usd != null && <div className="text-[11px] text-self">self-reported</div>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

