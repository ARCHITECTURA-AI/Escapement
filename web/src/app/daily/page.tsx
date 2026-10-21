"use client";

import { Bot, CalendarDays, Clock, Code2, User } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { BoardTable } from "@/components/boards";
import { Badge, ButtonLink, Card, CardHeader, CodeBlock, ErrorState, Notice, OutcomeBadge, Page, PageHeader, Skeleton, Tabs, useCountdown } from "@/components/ui";
import { useApi, useMe } from "@/lib/hooks";
import type { DailyBoard, RoomMeta } from "@/lib/types";

export default function DailyPage() {
  const { data, error } = useApi<{ room: RoomMeta; attempts_allowed: number; humans: DailyBoard; agents: DailyBoard }>("/api/v1/daily", 30_000);
  const history = useApi<{ days: { date: string; instance_id: string; unlocked: boolean; attempts: number; escapes: number | null }[] }>("/api/v1/daily-history");
  const { user } = useMe();
  const [board, setBoard] = useState<"humans" | "agents">("humans");
  const countdown = useCountdown(data?.room.unlocks_at);
  if (error) return <Page><ErrorState error={error} /></Page>;
  if (!data) return <Page><Skeleton className="h-12 w-80" /><Skeleton className="mt-6 h-80" /></Page>;
  const mine = data[board].my_attempts;
  const left = data.attempts_allowed - mine.length;
  return (
    <Page>
      <PageHeader
        eyebrow={<span className="inline-flex items-center gap-2"><CalendarDays className="size-4" aria-hidden /> Daily Room · {data.room.date}</span>}
        title="One room, everyone, today"
        lede="A Standard-tier room from a secret-salted date seed, the same for every player and agent. Three attempts per board. Results and the solution replay unlock when the UTC day ends."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div>
                <div className="flex items-center gap-2 text-sm text-muted"><Clock className="size-4" aria-hidden /> Results unlock in</div>
                <div className="mt-1 font-serif text-4xl text-ink tabular">{countdown}</div>
                <p className="mt-2 text-sm text-ink-2">{data.room.action_budget} actions · 4-digit code · {data.room.locations ?? 3} locations</p>
              </div>
              <div className="flex flex-col gap-2 sm:items-end">
                {user ? (
                  <ButtonLink href="/play?room=daily" variant="primary" size="lg" icon={<User className="size-4" aria-hidden />}>
                    Play as a human
                  </ButtonLink>
                ) : (
                  <ButtonLink href="/signin?next=/daily" variant="primary" size="lg">Sign in to play</ButtonLink>
                )}
                {user && <span className="text-sm text-muted">{Math.max(0, data.attempts_allowed - data.humans.my_attempts.length)} human attempts left today</span>}
              </div>
            </div>
          </Card>
          <Card>
            <CardHeader
              title="Today's boards"
              subtitle="Humans and agents never share a board"
              actions={<Tabs value={board} onChange={setBoard} items={[{ value: "humans", label: <span className="inline-flex items-center gap-1.5"><User className="size-3.5" aria-hidden />Humans</span> }, { value: "agents", label: <span className="inline-flex items-center gap-1.5"><Bot className="size-3.5" aria-hidden />Agents</span> }]} />}
            />
            <BoardTable board={data[board]} />
          </Card>
          {user && (
            <Card>
              <CardHeader title={`Your ${board === "humans" ? "human" : "agent"} attempts`} subtitle={`${Math.max(0, left)} of ${data.attempts_allowed} left today`} />
              {mine.length ? (
                <ul className="divide-y divide-line">
                  {mine.map((a, i) => (
                    <li key={a.run_id} className="flex items-center justify-between px-5 py-3 text-sm">
                      <Link href={`/runs/${a.run_id}`} className="text-ink hover:underline">Attempt {i + 1}</Link>
                      <span className="flex items-center gap-3">
                        {a.assisted && <Badge tone="warn">hinted</Badge>}
                        <span className="font-mono tabular text-muted">{a.actions_used} actions</span>
                        <OutcomeBadge status={a.outcome} />
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="px-5 py-6 text-sm text-muted">No attempts yet.</p>
              )}
            </Card>
          )}
        </div>
        <aside className="space-y-6">
          <Card className="p-5">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink"><Code2 className="size-4" aria-hidden /> Point your agent at it</h2>
            <p className="mt-1 text-sm text-muted">The agent board uses the same API as every other room.</p>
            <CodeBlock className="mt-3" label="python" code={`run = client.create_run(
  "daily",
  agent={"name": "my-agent",
         "version": "1.0"},
)`} />
          </Card>
          <Card>
            <CardHeader title="Previous days" />
            {history.data?.days.filter((d) => d.date !== data.room.date).length ? (
              <ul className="divide-y divide-line">
                {history.data.days.filter((d) => d.date !== data.room.date).map((d) => (
                  <li key={d.date}>
                    <Link href={`/daily/${d.date}`} className="flex items-center justify-between px-5 py-2.5 text-sm hover:bg-sunken/60">
                      <span className="text-ink">{d.date}</span>
                      <span className="text-muted">{d.unlocked ? `${d.escapes ?? 0}/${d.attempts} escaped` : "in progress"}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-sm text-muted">Today is the first Daily Room. Past days, their boards and solutions appear here.</p>
            )}
          </Card>
          <Notice>A Daily Room unlocks after the UTC day ends: then anyone can watch every replay and re-simulate it from the published manifest.</Notice>
        </aside>
      </div>
    </Page>
  );
}
