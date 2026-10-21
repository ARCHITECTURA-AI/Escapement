"use client";

import { EyeOff, Settings } from "lucide-react";
import { useParams } from "next/navigation";
import { VersionCard, VersionTimeline, type TimelinePoint } from "@/components/results";
import { Badge, ButtonLink, Card, CardHeader, Empty, ErrorState, Notice, Page, Skeleton, Stat } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { date } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { VersionResults } from "@/lib/types";

type Profile = {
  user: { id: string; handle: string; display_name: string | null; avatar_url: string | null; profile_public: boolean; joined: string; is_self: boolean; is_system: boolean };
  versions: VersionResults[];
  timeline: TimelinePoint[];
  human_play: { runs: number; escapes: number };
};

export default function ProfilePage() {
  const { handle } = useParams<{ handle: string }>();
  const { data, error } = useApi<Profile>(`/api/v1/profiles/${handle}`);
  if (error) {
    if (error instanceof ApiError && error.code === "FORBIDDEN")
      return (
        <Page>
          <Empty icon={<EyeOff className="size-8" aria-hidden />} title="This profile is private">
            Profiles are private by default. Sharing is a switch its owner controls. Certificates they share stay viewable by link.
          </Empty>
        </Page>
      );
    return <Page><ErrorState error={error} /></Page>;
  }
  if (!data) return <Page><Skeleton className="h-24 w-96" /><Skeleton className="mt-6 h-72" /></Page>;
  const u = data.user;
  const runs = data.versions.reduce((a, v) => a + v.total_runs, 0);
  return (
    <Page>
      <header className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          {u.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={u.avatar_url} alt="" className="size-16 rounded-2xl border border-line" />
          ) : (
            <div className="grid size-16 place-items-center rounded-2xl border border-line bg-surface font-serif text-2xl text-ink">{u.handle.slice(0, 1).toUpperCase()}</div>
          )}
          <div>
            <h1 className="font-serif text-4xl text-ink">{u.display_name ?? u.handle}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
              <span>@{u.handle}</span>
              <span>· joined {date(u.joined)}</span>
              {u.is_system && <Badge tone="signal">First-party reference agents</Badge>}
              {u.is_self && !u.profile_public && <Badge icon={<EyeOff className="size-3" aria-hidden />}>Private: only you can see this</Badge>}
            </div>
          </div>
        </div>
        {u.is_self && <ButtonLink href="/settings" icon={<Settings className="size-4" aria-hidden />}>Settings</ButtonLink>}
      </header>

      <div className="mb-6 grid grid-cols-2 gap-6 rounded-2xl border border-line bg-surface p-6 sm:grid-cols-4">
        <Stat label="Agent versions" value={data.versions.length} />
        <Stat label="Agent runs" value={runs} source="server" />
        <Stat label="Human runs" value={data.human_play.runs} />
        <Stat label="Human escapes" value={data.human_play.escapes} source="server" />
      </div>

      <Card className="mb-6">
        <CardHeader title="Versions over time" subtitle="Success rate with its 95% interval, per agent version (ranked results where available)" />
        <VersionTimeline points={data.timeline} />
      </Card>

      {data.versions.length === 0 ? (
        <Notice>No agent versions yet. {u.is_self && "Enter an agent from the Enter page; every new version becomes a point on this profile."}</Notice>
      ) : (
        <div className="space-y-5">
          {[...data.versions].reverse().map((v) => <VersionCard key={v.agent_version.id} v={v} owner={u.is_self} />)}
        </div>
      )}
    </Page>
  );
}
