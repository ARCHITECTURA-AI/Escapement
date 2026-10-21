"use client";

import clsx from "clsx";
import {
  ArrowRight,
  Backpack,
  Box,
  CheckCircle2,
  DoorOpen,
  Eye,
  Flag,
  KeyRound,
  Lightbulb,
  Lock,
  LockOpen,
  MapPin,
  Package,
  Sparkles,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import { actionText } from "@/lib/format";
import type { Action, Event, Observation, Result } from "@/lib/types";
import { Badge, Progress } from "./ui";

export function stateIcon(state: string[] | undefined) {
  if (!state) return null;
  if (state.includes("locked")) return <Lock className="size-3" aria-hidden />;
  if (state.includes("unlocked")) return <LockOpen className="size-3" aria-hidden />;
  return null;
}

export function StateChips({ state }: { state?: string[] }) {
  if (!state?.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {state.map((s) => (
        <Badge key={s} tone={s === "locked" ? "warn" : s === "open" || s === "unlocked" ? "good" : "neutral"} icon={s === "locked" ? <Lock className="size-3" aria-hidden /> : s === "unlocked" ? <LockOpen className="size-3" aria-hidden /> : null}>
          {s}
        </Badge>
      ))}
    </span>
  );
}

export function BudgetMeter({ obs }: { obs: Observation }) {
  const ratio = obs.actions_used / Math.max(1, obs.action_budget);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-sm">
        <span className="text-muted">Emergency clock</span>
        <span className="font-mono tabular text-ink">
          {obs.actions_remaining}
          <span className="text-faint"> / {obs.action_budget} left</span>
        </span>
      </div>
      <Progress value={obs.actions_used} max={obs.action_budget} tone={ratio > 0.85 ? "bad" : ratio > 0.6 ? "warn" : "ink"} label="Actions used" />
    </div>
  );
}

/** A read-only rendering of exactly what the agent saw. */
export function ObservationPanel({ obs, className, dense }: { obs: Observation; className?: string; dense?: boolean }) {
  return (
    <div className={clsx("space-y-4", className)}>
      <div>
        <div className="flex items-center gap-2 text-[13px] font-medium uppercase tracking-wider text-muted">
          <MapPin className="size-3.5" aria-hidden /> Location
        </div>
        <div className="mt-1 font-serif text-xl text-ink">{obs.location.name}</div>
        {!dense && <p className="mt-1 text-sm leading-relaxed text-ink-2">{obs.location.description}</p>}
      </div>
      <div>
        <div className="mb-1.5 text-[13px] font-medium uppercase tracking-wider text-muted">Visible</div>
        {obs.objects.length ? (
          <ul className="space-y-1">
            {obs.objects.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                <Box className="size-3.5 shrink-0 text-faint" aria-hidden />
                <span className="text-ink">{o.name}</span>
                <code className="font-mono text-[11.5px] text-faint">{o.id}</code>
                <StateChips state={o.state} />
                {o.in && <span className="text-xs text-muted">in {o.in.replaceAll("_", " ")}</span>}
                {o.portable && <Badge tone="neutral" icon={<Package className="size-3" aria-hidden />}>portable</Badge>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Nothing here.</p>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <div className="mb-1.5 text-[13px] font-medium uppercase tracking-wider text-muted">Exits</div>
          <ul className="space-y-1 text-sm">
            {obs.exits.map((e) => (
              <li key={e.id} className="flex items-center gap-2">
                <DoorOpen className="size-3.5 text-faint" aria-hidden />
                <span className="text-ink">{e.name}</span>
                <code className="font-mono text-[11.5px] text-faint">{e.id}</code>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-medium uppercase tracking-wider text-muted">Carrying</div>
          {obs.inventory.length ? (
            <ul className="space-y-1 text-sm">
              {obs.inventory.map((i) => (
                <li key={i.id} className="flex items-center gap-2">
                  <Backpack className="size-3.5 text-faint" aria-hidden />
                  <span className="text-ink">{i.name}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">Nothing.</p>
          )}
        </div>
      </div>
      <BudgetMeter obs={obs} />
    </div>
  );
}

const EVENT_LABEL: Record<string, (e: Event) => { icon: ReactNode; text: string; tone: "signal" | "good" | "warn" | "neutral" | "bad" }> = {
  clue_discovered: (e) => ({ icon: <Lightbulb className="size-3" aria-hidden />, text: `clue ${(e as { clue_id: string }).clue_id}`, tone: "signal" }),
  object_revealed: (e) => ({ icon: <Eye className="size-3" aria-hidden />, text: `revealed ${(e as { object_id: string }).object_id}`, tone: "neutral" }),
  item_taken: (e) => ({ icon: <Package className="size-3" aria-hidden />, text: `took ${(e as { item_id: string }).item_id}`, tone: "neutral" }),
  item_consumed: (e) => ({ icon: <Sparkles className="size-3" aria-hidden />, text: `used up ${(e as { item_id: string }).item_id}`, tone: "neutral" }),
  state_changed: (e) => ({ icon: <ArrowRight className="size-3" aria-hidden />, text: `${(e as { object_id: string }).object_id} ${(e as { state: string }).state}`, tone: "neutral" }),
  moved: (e) => ({ icon: <DoorOpen className="size-3" aria-hidden />, text: `moved to ${(e as { location_id: string }).location_id}`, tone: "neutral" }),
  unlocked: (e) => ({ icon: <KeyRound className="size-3" aria-hidden />, text: `unlocked ${(e as { object_id: string }).object_id}`, tone: "good" }),
  wrong_code: (e) => ({ icon: <XCircle className="size-3" aria-hidden />, text: `wrong code (${(e as { attempts: number }).attempts})`, tone: "bad" }),
  escaped: () => ({ icon: <Flag className="size-3" aria-hidden />, text: "escaped", tone: "good" }),
};

export function EventChips({ events }: { events: Event[] }) {
  if (!events?.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {events.map((e, i) => {
        const f = EVENT_LABEL[e.type];
        if (!f) return null;
        const m = f(e);
        return (
          <Badge key={i} tone={m.tone} icon={m.icon}>
            {m.text}
          </Badge>
        );
      })}
    </span>
  );
}

export function ResultLine({ action, result, seq, summary, className }: { action?: Action; result: Result; seq?: number; summary?: string; className?: string }) {
  return (
    <div className={clsx("rounded-xl border px-4 py-3", result.ok ? "border-line bg-surface" : "border-bad/25 bg-bad-soft/50", className)}>
      <div className="flex flex-wrap items-center gap-2">
        {result.ok ? <CheckCircle2 className="size-4 text-good" aria-label="Succeeded" /> : <XCircle className="size-4 text-bad" aria-label="Failed" />}
        {seq !== undefined && <span className="font-mono text-xs text-faint tabular">#{seq}</span>}
        {action && <code className="font-mono text-[13px] text-ink">{actionText(action)}</code>}
        {!result.ok && result.error && <Badge tone="bad">{result.error}</Badge>}
        {result.cost !== 1 && <Badge tone={result.cost > 1 ? "bad" : "neutral"}>cost {result.cost}</Badge>}
      </div>
      <p className="mt-1.5 text-[15px] leading-relaxed text-ink-2">{result.message}</p>
      {result.data?.clues?.length ? (
        <ul className="mt-2 space-y-1 border-l-2 border-signal/40 pl-3 text-sm">
          {result.data.clues.map((c) => (
            <li key={c.id}>
              <code className="font-mono text-xs text-signal-ink">{c.id}</code> <span className="text-ink-2">{c.text}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {result.events?.length ? (
        <div className="mt-2">
          <EventChips events={result.events} />
        </div>
      ) : null}
      {summary && (
        <div className="mt-2 rounded-lg border border-dashed border-self/40 bg-self-soft px-3 py-2 text-sm">
          <span className="text-xs font-medium text-self">Agent-provided summary · not a record of reasoning</span>
          <p className="mt-0.5 whitespace-pre-wrap break-words text-ink-2">{summary}</p>
        </div>
      )}
    </div>
  );
}
