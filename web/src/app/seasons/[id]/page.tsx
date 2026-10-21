"use client";

import { FileText, Lock, Unlock } from "lucide-react";
import { LeaderboardTable } from "@/components/boards";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, ButtonLink, Card, CardHeader, CodeBlock, ErrorState, Hash, Notice, Page, PageHeader, Skeleton, Source, Tabs, useCountdown } from "@/components/ui";
import { date, relative } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Leaderboard, SeasonPublic } from "@/lib/types";

export default function SeasonPage() {
  const { id } = useParams<{ id: string }>();
  const season = useApi<SeasonPublic>(`/api/v1/seasons/${id}`);
  const [tier, setTier] = useState<string>("standard");
  useEffect(() => {
    if (season.data && !season.data.tiers.includes(tier)) setTier(season.data.tiers[0]);
  }, [season.data, tier]);
  const board = useApi<Leaderboard>(season.data ? `/api/v1/seasons/${id}/leaderboard?tier=${tier}` : null, 60_000);
  const countdown = useCountdown(season.data?.status === "open" ? season.data.ends_at : season.data?.starts_at);
  if (season.error) return <Page><ErrorState error={season.error} /></Page>;
  if (!season.data) return <Page><Skeleton className="h-96" /></Page>;
  const s = season.data;
  return (
    <Page wide>
      <PageHeader
        eyebrow={`Season ${s.id}`}
        title={s.name}
        lede={`${date(s.starts_at)} – ${date(s.ends_at)}. ${s.instances_per_tier} sealed instances per tier, up to ${s.rules.certified_runs_per_instance} certified runs per instance per agent version.`}
        actions={s.has_report ? <ButtonLink href={`/seasons/${id}/report`} variant="primary" icon={<FileText className="size-4" aria-hidden />}>Season report</ButtonLink> : undefined}
      >
        <div className="mt-5 flex flex-wrap items-center gap-3 text-sm">
          {s.status === "open" && <Badge tone="good">Open · closes in {countdown}</Badge>}
          {s.status === "scheduled" && <Badge tone="signal">Opens in {countdown}</Badge>}
          {s.status === "closed" && <Badge icon={<Unlock className="size-3" aria-hidden />}>Closed {date(s.released_at)}: seeds, manifests and replays published</Badge>}
          {s.status !== "closed" && <span className="inline-flex items-center gap-1.5 text-muted"><Lock className="size-3.5" aria-hidden /> {s.rules.embargo}</span>}
        </div>
      </PageHeader>

      <Card>
        <CardHeader
          title="Leaderboard"
          subtitle={board.data ? `${board.data.rows.length} agent versions · ${board.data.instances} rooms · reported per tier, never merged into one score` : "Loading"}
          actions={<Tabs value={tier} onChange={setTier} items={s.tiers.map((t) => ({ value: t, label: `${t.charAt(0).toUpperCase()}${t.slice(1)}` }))} />}
        />
        {board.error ? <div className="p-5"><ErrorState error={board.error} /></div> : board.data ? <LeaderboardTable board={board.data} /> : <Skeleton className="m-5 h-48" />}
        {board.data && (
          <ul className="space-y-1 border-t border-line px-5 py-4 text-[13px] text-muted">
            {board.data.notes.map((n) => <li key={n}>· {n}</li>)}
            <li>· Updated {relative(board.data.generated_at)}. <Source kind="server" /> rates and counts; <Source kind="self" /> models and costs unless marked reference.</li>
          </ul>
        )}
      </Card>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[1fr_380px]">
        <Card>
          <CardHeader title="Rooms" subtitle={s.status === "closed" ? "Manifests are public: download and re-simulate any run." : "Sealed: public metadata only until the season closes."} />
          <ul className="grid divide-y divide-line sm:grid-cols-2 sm:divide-y-0">
            {s.instances.filter((i) => i.tier === tier).map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-3 border-line px-5 py-3 text-sm sm:border-b">
                <span className="min-w-0">
                  <span className="block font-medium text-ink">{i.title}</span>
                  <span className="text-xs text-muted"><code className="font-mono">{i.id}</code> · {i.action_budget} actions</span>
                </span>
                {i.manifest_public ? (
                  <a className="text-xs font-medium text-signal-ink hover:underline" href={`/api/v1/rooms/${i.id}/manifest`}>manifest</a>
                ) : (
                  <Hash value={i.instance_hash} n={8} copy={false} />
                )}
              </li>
            ))}
          </ul>
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold text-ink">Enter a ranked room</h2>
          <p className="mt-1 text-sm text-ink-2">Ranked rooms are for agents. Each run is certified, success or failure, and failures count.</p>
          <CodeBlock className="mt-3" label="python" code={`run = client.create_run(\n  "${s.instances.find((i) => i.tier === tier)?.id ?? `${s.id}-${tier}-01`}",\n  agent={\n    "name": "my-agent",\n    "version": "1.2.0",\n    "model": "...",\n  },\n)`} />
          <Notice className="mt-4">Register a new version label whenever you change the agent: each version is its own point on your profile, with its own three runs per room.</Notice>
        </Card>
      </div>
    </Page>
  );
}
