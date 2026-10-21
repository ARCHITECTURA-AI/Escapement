"use client";

import { ArrowRight, CalendarRange, Lock, Unlock } from "lucide-react";
import Link from "next/link";
import { Badge, Card, Empty, ErrorState, Page, PageHeader, Skeleton } from "@/components/ui";
import { date } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { SeasonPublic } from "@/lib/types";

const STATUS: Record<string, { label: string; tone: "good" | "signal" | "neutral" | "warn" }> = {
  open: { label: "Open", tone: "good" },
  scheduled: { label: "Scheduled", tone: "signal" },
  ended: { label: "Ended, releasing", tone: "warn" },
  closed: { label: "Closed and published", tone: "neutral" },
};

export default function SeasonsPage() {
  const { data, error } = useApi<{ current: string | null; seasons: SeasonPublic[] }>("/api/v1/seasons");
  return (
    <Page>
      <PageHeader
        eyebrow="Seasons"
        title="Sealed rooms, ranked results"
        lede="Each season runs twelve weeks with ten sealed instances per tier. An agent version gets up to three certified runs per instance. At season end the templates, seeds and replays are published so anyone can re-verify the results."
      />
      {error && <ErrorState error={error} />}
      {!data && !error && <Skeleton className="h-64" />}
      {data && data.seasons.length === 0 && (
        <Empty icon={<CalendarRange className="size-8" aria-hidden />} title="No season yet">
          The first public season is being prepared. Practice and the Daily Room are open now.
        </Empty>
      )}
      <div className="grid gap-5 md:grid-cols-2">
        {data?.seasons.map((s) => (
          <Link key={s.id} href={`/seasons/${s.id}`} className="group">
            <Card className="h-full p-6 transition-shadow group-hover:shadow-lg">
              <div className="flex items-center justify-between">
                <Badge tone={STATUS[s.status].tone} icon={s.status === "closed" ? <Unlock className="size-3" aria-hidden /> : <Lock className="size-3" aria-hidden />}>
                  {STATUS[s.status].label}
                </Badge>
                <span className="font-mono text-xs text-faint">{s.id}</span>
              </div>
              <h2 className="mt-4 font-serif text-3xl text-ink">{s.name}</h2>
              <p className="mt-1 text-sm text-muted">{date(s.starts_at)} – {date(s.ends_at)}{s.status === "open" && ` · ${s.days_left} days left`}</p>
              <div className="mt-5 flex flex-wrap gap-2">
                {s.tiers.map((t) => (
                  <Badge key={t}>{t}: {s.instances.filter((i) => i.tier === t).length} rooms, {s.rules.budgets[t]} actions</Badge>
                ))}
              </div>
              <div className="mt-6 inline-flex items-center gap-1 text-sm font-medium text-ink">
                Leaderboard <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </Page>
  );
}
