"use client";

import { AlertTriangle, ArrowLeft, Info, Milestone, Stethoscope } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Badge, ButtonLink, Card, CardHeader, ErrorState, Notice, OutcomeBadge, Page, PageHeader, Skeleton, Source, Stat } from "@/components/ui";
import { pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Finding, RunSummary } from "@/lib/types";

type Clinic = {
  note: string;
  findings: Finding[];
  metrics: { steps: number; actions_used: number; invalid_action_rate: number | null; repeated_action_rate: number | null; malformed: number; clues_found: number; wrong_codes: number };
  milestones: { id: string; label: string; seq: number; actions_used: number }[] | null;
  milestone_comparison_unavailable: string | null;
  run: RunSummary;
};

export default function ClinicPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useApi<Clinic>(`/api/v1/runs/${id}/clinic`);
  if (error) return <Page><ErrorState error={error} /><div className="mt-4"><ButtonLink href={`/runs/${id}`} icon={<ArrowLeft className="size-4" aria-hidden />}>Back to the run</ButtonLink></div></Page>;
  if (!data) return <Page><Skeleton className="h-12 w-72" /><Skeleton className="mt-6 h-96" /></Page>;
  const m = data.metrics;
  return (
    <Page>
      <PageHeader
        eyebrow={<span className="inline-flex items-center gap-2"><Stethoscope className="size-4" aria-hidden /> Trace Clinic</span>}
        title={<>Why this run went the way it did</>}
        lede="Failure analysis on your own run. Every label below is a heuristic, not ground truth: use it to decide where to look in the replay."
        actions={<ButtonLink href={`/runs/${id}`} icon={<ArrowLeft className="size-4" aria-hidden />}>Back to the replay</ButtonLink>}
      >
        <div className="mt-5 flex flex-wrap items-center gap-2 text-sm text-ink-2">
          <OutcomeBadge status={data.run.status} />
          <span>{data.run.room.title}</span>
          <span className="text-faint">·</span>
          <span>{data.run.agent_type === "human" ? "Human player" : `${data.run.agent.name} ${data.run.agent.version ?? ""}`}</span>
        </div>
      </PageHeader>

      <div className="grid grid-cols-2 gap-6 rounded-2xl border border-line bg-surface p-6 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Actions used" value={m.actions_used} source="server" />
        <Stat label="Invalid-action rate" value={pct(m.invalid_action_rate)} source="server" />
        <Stat label="Repeated-action rate" value={pct(m.repeated_action_rate)} source="server" />
        <Stat label="Clues found" value={m.clues_found} />
        <Stat label="Wrong codes" value={m.wrong_codes} />
        <Stat label="Malformed" value={m.malformed} />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-serif text-2xl text-ink">Findings</h2>
            <Source kind="heuristic" />
          </div>
          {data.findings.length === 0 ? (
            <Notice>No findings: the run made steady progress.</Notice>
          ) : (
            <ul className="space-y-3">
              {data.findings.map((f, i) => (
                <li key={i}>
                  <Card className="p-5">
                    <div className="flex items-start gap-3">
                      {f.severity === "warn" ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" aria-label="Worth a look" /> : <Info className="mt-0.5 size-4 shrink-0 text-muted" aria-label="Note" />}
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-ink">{f.title}</h3>
                          <Badge tone="warn">heuristic</Badge>
                        </div>
                        <p className="mt-1 text-sm leading-relaxed text-ink-2">{f.detail}</p>
                        {f.steps.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                            <span className="text-muted">Steps</span>
                            {f.steps.slice(0, 12).map((s) => (
                              <Link key={s} href={`/runs/${id}#step-${s}`} className="rounded-md border border-line px-1.5 py-0.5 font-mono text-ink-2 hover:bg-sunken">
                                {s}
                              </Link>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>
        <aside>
          <Card>
            <CardHeader title="Milestones" icon={<Milestone className="size-4" aria-hidden />} subtitle="Private progress markers, never sent to agents" />
            <div className="p-5">
              {data.milestones ? (
                <ol className="relative space-y-4 border-l border-line pl-5">
                  {data.milestones.map((ms) => (
                    <li key={ms.id}>
                      <span className="absolute -left-[5px] mt-1.5 size-2.5 rounded-full bg-ink" aria-hidden />
                      <div className="text-sm font-medium text-ink">{ms.label}</div>
                      <div className="text-xs text-muted">step {ms.seq} · {ms.actions_used} actions used</div>
                    </li>
                  ))}
                  {data.milestones.length === 0 && <li className="text-sm text-muted">No milestone reached.</li>}
                </ol>
              ) : (
                <p className="text-sm text-muted">{data.milestone_comparison_unavailable}</p>
              )}
            </div>
          </Card>
          <p className="mt-4 text-xs leading-relaxed text-muted">{data.note} A replay of a ranked room contains only the public observations you already saw; others cannot view it until the season closes.</p>
        </aside>
      </div>
    </Page>
  );
}
