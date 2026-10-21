"use client";

import { Download, Gamepad2, Lock } from "lucide-react";
import { useParams } from "next/navigation";
import { Badge, ButtonLink, Card, CardHeader, CodeBlock, ErrorState, Hash, KV, Page, PageHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { RoomMeta } from "@/lib/types";

export default function RoomPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useApi<RoomMeta & { locations?: number }>(`/api/v1/rooms/${id}`);
  if (error) return <Page><ErrorState error={error} /></Page>;
  if (!data) return <Page><Skeleton className="h-80" /></Page>;
  const playable = data.kind === "practice" || data.kind === "daily" || data.kind === "research";
  return (
    <Page>
      <PageHeader
        eyebrow={`${data.family_title ?? "Room"} · ${data.kind}`}
        title={data.title}
        lede={data.intro}
        actions={
          <>
            {playable && data.kind !== "research" && <ButtonLink href={`/play?room=${data.kind}`} variant="primary" icon={<Gamepad2 className="size-4" aria-hidden />}>Play</ButtonLink>}
            {data.manifest_public && <ButtonLink href={`/api/v1/rooms/${id}/manifest`} external icon={<Download className="size-4" aria-hidden />}>Manifest</ButtonLink>}
          </>
        }
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Public metadata" subtitle="What anyone, including agents, can know about this room" />
          <dl className="px-5 py-2">
            <KV k="Tier" v={<span className="capitalize">{data.tier}</span>} />
            <KV k="Goal" v={data.goal} />
            <KV k="Action budget" v={String(data.action_budget)} />
            <KV k="Malformed limit" v={String(data.malformed_limit ?? 3)} />
            <KV k="Wrong codes" v={`${data.wrong_code_free_attempts ?? 3} free per lock, then +${data.wrong_code_penalty ?? 2} actions each`} />
            <KV k="Instance hash" v={<Hash value={data.instance_hash} />} />
            {data.min_length != null && <KV k="Shortest solution" v={`${data.min_length} actions (${data.optimality === "proven" ? "proven minimum" : "best verified"})`} />}
          </dl>
        </Card>
        <Card className="p-5">
          {data.manifest_public ? (
            <>
              <Badge tone="good">Manifest public</Badge>
              <p className="mt-3 text-sm text-ink-2">Anyone can re-simulate any run on this room through the pinned engine:</p>
              <CodeBlock className="mt-3" code={`curl -sO ${typeof window !== "undefined" ? window.location.origin : ""}/api/v1/rooms/${id}/manifest
escapement replay RUN.replay.json --manifest manifest`} />
            </>
          ) : (
            <>
              <Badge icon={<Lock className="size-3" aria-hidden />}>Sealed</Badge>
              <p className="mt-3 text-sm text-ink-2">The manifest, seed and verified solution are held in a table the public API cannot read. They are published when this room&apos;s results are released.</p>
            </>
          )}
        </Card>
      </div>
    </Page>
  );
}
