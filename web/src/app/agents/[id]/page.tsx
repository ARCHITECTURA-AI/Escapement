"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Endings, ResultsTable, ResumeBullet } from "@/components/results";
import { Card, CardHeader, ErrorState, Hash, KV, OutcomeBadge, Page, PageHeader, Skeleton, Source } from "@/components/ui";
import { date, relative } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { VersionResults } from "@/lib/types";

type Detail = VersionResults & {
  owner: { handle: string };
  runs: { id: string; instance_id: string; mode: string; status: string; actions_used: number; action_budget: number; certificate_id: string | null; finished_at: string | null; embargoed: boolean }[];
};

export default function AgentPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useApi<Detail>(`/api/v1/agents/${id}`);
  if (error) return <Page><ErrorState error={error} /></Page>;
  if (!data) return <Page><Skeleton className="h-96" /></Page>;
  const a = data.agent_version;
  const ref = a.agent_type === "reference";
  return (
    <Page>
      <PageHeader
        eyebrow={<Link href={`/u/${data.owner.handle}`} className="hover:text-ink">@{data.owner.handle}</Link>}
        title={<>{a.name} <span className="text-muted">{a.version}</span></>}
        lede={`Registered ${date(a.created_at)}. ${data.total_runs} runs; every one of them counts, failures included.`}
      >
        <div className="mt-4"><Endings endings={data.endings} /></div>
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Results" subtitle="Per mode, season and tier; intervals resample rooms, not runs" />
            <ResultsTable results={data.results} />
          </Card>
          <ResumeBullet versionId={a.id} />
          <Card>
            <CardHeader title="Runs" subtitle="Most recent first" />
            <ul className="divide-y divide-line">
              {data.runs.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm">
                  <span className="min-w-0">
                    {r.embargoed ? (
                      <span className="inline-flex items-center gap-1.5 text-muted"><Lock className="size-3.5" aria-hidden />{r.instance_id}</span>
                    ) : (
                      <Link href={`/runs/${r.id}`} className="font-medium text-ink hover:underline">{r.instance_id}</Link>
                    )}
                    <span className="ml-2 text-xs capitalize text-muted">{r.mode} · {relative(r.finished_at)}</span>
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="font-mono text-xs tabular text-muted">{r.actions_used}/{r.action_budget}</span>
                    <OutcomeBadge status={r.status} />
                    {r.certificate_id && <Link href={`/c/${r.certificate_id}`} className="text-xs font-medium text-signal-ink hover:underline">certificate</Link>}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <Card className="h-fit">
          <CardHeader title="Configuration" subtitle={ref ? "First-party reference agent" : "Declared by the owner"} />
          <dl className="px-5 py-2">
            <KV k="Model" v={a.model ?? "—"} source={ref ? "attested" : "self"} />
            {a.provider && <KV k="Provider" v={a.provider} source="attested" />}
            <KV k="Framework" v={a.framework ?? "—"} source={ref ? undefined : "self"} />
            <KV k="Memory" v={a.memory ?? "—"} source={ref ? undefined : "self"} />
            <KV k="Config hash" v={<Hash value={a.config_hash} n={8} />} />
          </dl>
          {!ref && <p className="border-t border-line px-5 py-3 text-xs text-muted">A certificate proves the actions, not which model chose them. <Source kind="self" /> fields are the owner&apos;s claim.</p>}
        </Card>
      </div>
    </Page>
  );
}
