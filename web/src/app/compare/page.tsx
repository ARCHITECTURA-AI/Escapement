"use client";

import clsx from "clsx";
import { Columns3, Flag, ListTree, Plus, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { EventChips, ObservationPanel } from "@/components/observation";
import { PlaybackControls, markersFor, observationAt, usePlayback } from "@/components/replay-player";
import { Badge, Button, Card, Empty, ErrorState, Notice, OutcomeBadge, Page, PageHeader, Skeleton, Tabs } from "@/components/ui";
import { actionText } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Replay, RunSummary, Step } from "@/lib/types";

type CompareData = { instance_id: string; runs: { run: RunSummary; replay: Replay }[]; max_steps: number };

function Picker({ initial }: { initial: string[] }) {
  const router = useRouter();
  const [ids, setIds] = useState<string[]>(initial.length ? initial : ["", ""]);
  const { data: mine } = useApi<{ runs: RunSummary[] }>("/api/v1/runs?limit=50");
  const set = (i: number, v: string) => setIds((x) => x.map((y, j) => (j === i ? v.trim() : y)));
  const valid = ids.filter(Boolean);
  return (
    <Card className="p-5">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid.length >= 2) router.push(`/compare?runs=${valid.join(",")}`);
        }}
      >
        <p className="text-sm text-ink-2">Pick two or three runs on the same room instance. Paste run ids from Watch pages or choose from your recent runs.</p>
        {ids.map((v, i) => (
          <div key={i} className="flex gap-2">
            <label className="sr-only" htmlFor={`run-${i}`}>Run {i + 1}</label>
            <input id={`run-${i}`} list="my-runs" value={v} onChange={(e) => set(i, e.target.value)} placeholder={`Run ${i + 1} id`} className="h-10 flex-1 rounded-lg border border-line-strong bg-surface px-3 font-mono text-sm text-ink" />
            {ids.length > 2 && (
              <Button type="button" variant="ghost" onClick={() => setIds((x) => x.filter((_, j) => j !== i))} aria-label="Remove">
                <X className="size-4" aria-hidden />
              </Button>
            )}
          </div>
        ))}
        <datalist id="my-runs">
          {mine?.runs.filter((r) => r.status !== "in_progress").map((r) => (
            <option key={r.id} value={r.id}>{`${r.agent.name ?? "human"} ${r.agent.version ?? ""} · ${r.room.title} · ${r.status}`}</option>
          ))}
        </datalist>
        <div className="flex gap-2">
          {ids.length < 3 && (
            <Button type="button" variant="ghost" onClick={() => setIds((x) => [...x, ""])} icon={<Plus className="size-4" aria-hidden />}>
              Add a third run
            </Button>
          )}
          <Button type="submit" variant="primary" disabled={valid.length < 2} icon={<Columns3 className="size-4" aria-hidden />}>
            Compare
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Column({ entry, index, mode }: { entry: { run: RunSummary; replay: Replay }; index: number; mode: "summary" | "trace" }) {
  const steps = entry.replay.steps;
  const finished = index >= steps.length;
  const obs = observationAt(entry.replay.initial_observation, steps, index);
  const step: Step | null = index > 0 && index <= steps.length ? steps[index - 1] : null;
  return (
    <Card className="flex min-w-0 flex-col">
      <div className="border-b border-line px-5 py-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate font-semibold text-ink">{entry.run.agent_type === "human" ? "Human player" : `${entry.run.agent.name} ${entry.run.agent.version ?? ""}`}</div>
            <div className="truncate text-xs text-muted">{entry.run.agent.model ?? "model not declared"} · self-reported</div>
          </div>
          <OutcomeBadge status={entry.run.status} />
        </div>
        {finished && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-sunken px-3 py-2 text-[13px] text-ink-2">
            <Flag className="size-3.5" aria-hidden /> Finished at step {steps.length}: {entry.run.status_label.toLowerCase()}. No automatic reset.
          </div>
        )}
      </div>
      <div className="flex-1 space-y-4 p-5">
        {step ? (
          <div className={clsx("rounded-xl border px-3 py-2.5", step.result.ok ? "border-line" : "border-bad/30 bg-bad-soft/40")}>
            <code className={clsx("font-mono text-[13px]", step.result.ok ? "text-ink" : "text-bad")}>{actionText(step.action)}</code>
            <p className="mt-1 text-sm text-ink-2">{step.result.message}</p>
            <div className="mt-1.5"><EventChips events={step.result.events.filter((e) => e.type !== "moved")} /></div>
          </div>
        ) : (
          <p className="text-sm text-muted">{index === 0 ? "Start of run." : ""}</p>
        )}
        {mode === "trace" ? (
          <ObservationPanel obs={obs} dense />
        ) : (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-muted">Location</dt><dd className="text-ink">{obs.location.name}</dd></div>
            <div><dt className="text-muted">Budget left</dt><dd className="font-mono tabular text-ink">{obs.actions_remaining}</dd></div>
            <div><dt className="text-muted">Carrying</dt><dd className="text-ink">{obs.inventory.map((i) => i.name).join(", ") || "nothing"}</dd></div>
            <div><dt className="text-muted">Clues</dt><dd className="font-mono tabular text-ink">{obs.journal_entries}</dd></div>
          </dl>
        )}
      </div>
    </Card>
  );
}

function CompareInner() {
  const params = useSearchParams();
  const ids = (params.get("runs") ?? "").split(",").filter(Boolean);
  const { data, error } = useApi<CompareData>(ids.length >= 2 ? `/api/v1/compare?runs=${ids.join(",")}` : null);
  const [mode, setMode] = useState<"summary" | "trace">("summary");
  const longest = data?.runs.reduce((a, b) => (b.replay.steps.length > a.replay.steps.length ? b : a), data.runs[0]);
  const pb = usePlayback(data?.max_steps ?? 0);
  const markers = useMemo(() => (longest ? markersFor(longest.replay.steps) : { clue: [], invalid: [], unlock: [], outcome: [] }), [longest]);

  return (
    <Page wide>
      <PageHeader
        eyebrow="Compare"
        title="Agent versions, side by side"
        lede="Runs on the same room instance, synced by action number rather than model response time. Each column keeps its own state; a finished run stays finished."
        actions={data && <Tabs value={mode} onChange={setMode} items={[{ value: "summary", label: <span className="inline-flex items-center gap-1.5"><Columns3 className="size-4" aria-hidden />Summary</span> }, { value: "trace", label: <span className="inline-flex items-center gap-1.5"><ListTree className="size-4" aria-hidden />Trace</span> }]} />}
      />
      {ids.length < 2 && <Picker initial={ids} />}
      {error && (
        <div className="space-y-4">
          <ErrorState error={error} />
          <Picker initial={ids} />
        </div>
      )}
      {ids.length >= 2 && !data && !error && <Skeleton className="h-96" />}
      {data && longest && (
        <div className="space-y-5">
          <Notice>
            Paired comparison on instance <code className="font-mono">{data.instance_id}</code>. {data.runs.length} runs, longest {data.max_steps} steps. <Badge>same room, same seed</Badge>
          </Notice>
          <Card className="p-5">
            <PlaybackControls pb={pb} steps={longest.replay.steps} markers={markers} showKeys={false} />
          </Card>
          <div className={clsx("grid gap-5", data.runs.length === 3 ? "lg:grid-cols-3" : "lg:grid-cols-2")}>
            {data.runs.map((e) => (
              <Column key={e.run.id} entry={e} index={pb.index} mode={mode} />
            ))}
          </div>
        </div>
      )}
      {ids.length >= 2 && data && data.runs.length === 0 && <Empty title="Nothing to compare" />}
    </Page>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<Page><Skeleton className="h-96" /></Page>}>
      <CompareInner />
    </Suspense>
  );
}
