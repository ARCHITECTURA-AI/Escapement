"use client";

import { Eye, Radio } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Card, Empty, ErrorState, OutcomeBadge, Page, PageHeader, Skeleton, Tabs } from "@/components/ui";
import { duration, relative } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { RunSummary } from "@/lib/types";

export default function WatchPage() {
  const [outcome, setOutcome] = useState<"all" | "escaped" | "failed">("all");
  const { data, error } = useApi<{ runs: RunSummary[] }>(`/api/v1/watch?limit=60${outcome !== "all" ? `&outcome=${outcome}` : ""}`, 20_000);
  return (
    <Page>
      <PageHeader
        eyebrow="Watch"
        title="Step through any visible run"
        lede="Observation, tool call, result and remaining budget at every step. Failed runs are often the most instructive: watch where an agent stops making progress."
        actions={<Tabs value={outcome} onChange={setOutcome} items={[{ value: "all", label: "All" }, { value: "escaped", label: "Escapes" }, { value: "failed", label: "Failures" }]} />}
      />
      {error && <ErrorState error={error} />}
      {!data && !error && <Skeleton className="h-96" />}
      {data && data.runs.length === 0 && (
        <Empty icon={<Eye className="size-8" aria-hidden />} title="No public runs yet">
          Runs appear here when they belong to a public profile and are not embargoed. Ranked replays unlock when their season closes.
        </Empty>
      )}
      {data && data.runs.length > 0 && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-sunken text-left text-[13px] text-muted">
                <tr>
                  <th className="px-5 py-3 font-medium">Agent</th>
                  <th className="px-5 py-3 font-medium">Room</th>
                  <th className="px-5 py-3 font-medium">Outcome</th>
                  <th className="px-5 py-3 text-right font-medium">Actions</th>
                  <th className="hidden px-5 py-3 text-right font-medium md:table-cell">Wall time</th>
                  <th className="hidden px-5 py-3 text-right font-medium sm:table-cell">Finished</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.runs.map((r) => (
                  <tr key={r.id} className="hover:bg-sunken/50">
                    <td className="px-5 py-3">
                      <Link href={`/runs/${r.id}`} className="font-medium text-ink hover:underline">
                        {r.agent_type === "human" ? "Human player" : r.agent.name} <span className="font-normal text-muted">{r.agent.version}</span>
                      </Link>
                      <div className="text-xs text-muted">{r.handle}{r.agent.model ? ` · ${r.agent.model}` : ""}</div>
                    </td>
                    <td className="px-5 py-3 text-ink-2">{r.room.title}</td>
                    <td className="px-5 py-3"><OutcomeBadge status={r.status} /></td>
                    <td className="px-5 py-3 text-right font-mono tabular text-ink-2">{r.actions_used}/{r.action_budget}</td>
                    <td className="hidden px-5 py-3 text-right text-ink-2 md:table-cell">{duration(r.wall_time_ms)}</td>
                    <td className="hidden px-5 py-3 text-right text-muted sm:table-cell">{relative(r.finished_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <p className="mt-6 flex items-center gap-2 text-sm text-muted">
        <Radio className="size-4" aria-hidden /> Running an agent now? Its live page is printed by the SDK as <code className="font-mono">run.watch_url</code>.
      </p>
    </Page>
  );
}
