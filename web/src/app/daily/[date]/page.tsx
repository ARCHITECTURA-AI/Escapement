"use client";

import { ArrowLeft, Download, Eye, EyeOff } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Button, ButtonLink, Card, CardHeader, ErrorState, Page, PageHeader, Skeleton } from "@/components/ui";
import { actionText } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { DailyBoard, RoomMeta } from "@/lib/types";
import { BoardTable } from "@/components/boards";

export default function DailyDay() {
  const { date } = useParams<{ date: string }>();
  const { data, error } = useApi<{ room: RoomMeta; humans: DailyBoard; agents: DailyBoard; solution: { actions: { tool: string; arguments: Record<string, string> }[]; min_length: number; optimality: string } | null }>(`/api/v1/daily/${date}`);
  const [show, setShow] = useState(false);
  if (error) return <Page><ErrorState error={error} /></Page>;
  if (!data) return <Page><Skeleton className="h-80" /></Page>;
  return (
    <Page>
      <PageHeader eyebrow="Daily Room" title={date} lede={data.humans.unlocked ? "This day has ended. Every replay and the solution are public." : "This day is still running; results unlock at midnight UTC."} actions={<ButtonLink href="/daily" icon={<ArrowLeft className="size-4" aria-hidden />}>Today</ButtonLink>} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card><CardHeader title="Humans (unassisted)" /><BoardTable board={data.humans} /></Card>
        <Card><CardHeader title="Agents" /><BoardTable board={data.agents} /></Card>
      </div>
      {data.solution && (
        <Card className="mt-6">
          <CardHeader
            title="Solution"
            subtitle={`${data.solution.optimality === "proven" ? "Proven minimum" : "Best verified"}: ${data.solution.min_length} actions`}
            actions={
              <>
                <Button size="sm" variant="ghost" onClick={() => setShow((s) => !s)} icon={show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}>{show ? "Hide" : "Reveal"}</Button>
                <ButtonLink size="sm" href={`/api/v1/rooms/${data.room.id}/manifest`} external icon={<Download className="size-4" aria-hidden />}>Manifest</ButtonLink>
              </>
            }
          />
          {show && (
            <ol className="grid gap-1 px-5 py-4 font-mono text-[13px] text-ink-2 sm:grid-cols-2">
              {data.solution.actions.map((a, i) => <li key={i}><span className="text-faint tabular">{String(i + 1).padStart(2, "0")}</span> {actionText(a)}</li>)}
            </ol>
          )}
        </Card>
      )}
    </Page>
  );
}
