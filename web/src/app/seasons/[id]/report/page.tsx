"use client";

import { ArrowLeft } from "lucide-react";
import { useParams } from "next/navigation";
import { ButtonLink, Card, CardHeader, ErrorState, Notice, Page, PageHeader, Skeleton } from "@/components/ui";
import { date, endingLabel } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Leaderboard } from "@/lib/types";
import { LeaderboardTable } from "@/components/boards";

type Report = {
  season_id: string;
  name: string;
  starts_at: string;
  ends_at: string;
  released_at: string;
  engine_version: string;
  generalization_level: string;
  participants: number;
  tiers: Record<string, { budget: number; parameters: Record<string, number>; instances: { id: string; instance_hash: string; optimality: string; min_length: number | null; seed: string | null; runs: number; escapes: number }[]; endings: Record<string, number>; leaderboard: Leaderboard }>;
  reproduce: string;
  limits: string[];
};

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useApi<Report>(`/api/v1/seasons/${id}/report`);
  if (error) return <Page><ErrorState error={error} /></Page>;
  if (!data) return <Page><Skeleton className="h-96" /></Page>;
  return (
    <Page wide>
      <PageHeader
        eyebrow="Season report"
        title={data.name}
        lede={`${date(data.starts_at)} – ${date(data.ends_at)}, released ${date(data.released_at)}. ${data.participants} participants. Engine ${data.engine_version}. Generalization level: ${data.generalization_level}.`}
        actions={<ButtonLink href={`/seasons/${id}`} icon={<ArrowLeft className="size-4" aria-hidden />}>Season</ButtonLink>}
      />
      <Notice className="mb-6" title="How to reproduce">{data.reproduce}</Notice>
      {Object.entries(data.tiers).map(([tier, t]) => (
        <section key={tier} className="mb-10">
          <h2 className="mb-3 font-serif text-3xl capitalize text-ink">{tier} tier</h2>
          <p className="mb-4 text-sm text-ink-2">
            Budget {t.budget} actions · {t.parameters.locations} locations · {t.parameters.irrelevant_objects} irrelevant objects · clue composition depth {t.parameters.clue_composition_depth} · {t.parameters.code_digits}-digit codes.
          </p>
          <Card className="mb-5"><LeaderboardTable board={t.leaderboard} /></Card>
          <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
            <Card>
              <CardHeader title="Instances" subtitle="Seeds and minimum solution lengths, published at season close" />
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-sunken text-left text-[13px] text-muted">
                    <tr><th className="px-4 py-2.5 font-medium">Room</th><th className="px-4 py-2.5 font-medium">Seed</th><th className="px-4 py-2.5 text-right font-medium">Shortest</th><th className="px-4 py-2.5 text-right font-medium">Escapes / runs</th></tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {t.instances.map((i) => (
                      <tr key={i.id}>
                        <td className="px-4 py-2.5 font-mono text-[13px]">{i.id}</td>
                        <td className="px-4 py-2.5 font-mono text-[12px] text-muted">{i.seed?.slice(0, 16)}…</td>
                        <td className="px-4 py-2.5 text-right tabular">{i.min_length ?? "—"}{i.optimality === "proven" ? "" : "*"}</td>
                        <td className="px-4 py-2.5 text-right font-mono tabular">{i.escapes}/{i.runs}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card>
              <CardHeader title="Every ending" subtitle="Failures stay in reports and aggregates" />
              <ul className="divide-y divide-line">
                {Object.entries(t.endings).map(([k, v]) => (
                  <li key={k} className="flex justify-between px-5 py-2.5 text-sm"><span className="text-ink-2">{endingLabel(k)}</span><span className="font-mono tabular">{v}</span></li>
                ))}
                {Object.keys(t.endings).length === 0 && <li className="px-5 py-4 text-sm text-muted">No runs.</li>}
              </ul>
            </Card>
          </div>
        </section>
      ))}
      <Card className="p-6">
        <h2 className="font-semibold text-ink">Limits of these results</h2>
        <ul className="mt-2 space-y-1.5 text-sm text-ink-2">{data.limits.map((l) => <li key={l}>· {l}</li>)}</ul>
      </Card>
    </Page>
  );
}
