"use client";

import clsx from "clsx";
import { ChevronLeft, ChevronRight, Flag, KeyRound, Lightbulb, Pause, Play, SkipBack, SkipForward, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Observation, Step } from "@/lib/types";
import { Kbd } from "./ui";

export type MarkerKind = "clue" | "invalid" | "unlock" | "outcome";

export function markersFor(steps: Step[]): Record<MarkerKind, number[]> {
  const out: Record<MarkerKind, number[]> = { clue: [], invalid: [], unlock: [], outcome: [] };
  steps.forEach((s, i) => {
    const idx = i + 1;
    if (s.result.events?.some((e) => e.type === "clue_discovered")) out.clue.push(idx);
    if (!s.result.ok && !s.system) out.invalid.push(idx);
    if (s.result.events?.some((e) => e.type === "unlocked" || e.type === "escaped") || /blast door rolls up|power restored/i.test(s.result.message)) out.unlock.push(idx);
    if (s.status !== "in_progress") out.outcome.push(idx);
  });
  return out;
}

const MARKER_META: Record<MarkerKind, { label: string; icon: typeof Lightbulb; cls: string }> = {
  clue: { label: "Clue", icon: Lightbulb, cls: "text-signal" },
  invalid: { label: "Invalid", icon: XCircle, cls: "text-bad" },
  unlock: { label: "Unlock", icon: KeyRound, cls: "text-good" },
  outcome: { label: "Outcome", icon: Flag, cls: "text-ink" },
};

export function observationAt(initial: Observation, steps: Step[], index: number): Observation {
  return index <= 0 ? initial : steps[Math.min(index, steps.length) - 1].observation;
}

/** Controlled playback state shared by Watch and Compare. */
export function usePlayback(length: number, opts: { follow?: boolean } = {}) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [following, setFollowing] = useState(Boolean(opts.follow));

  useEffect(() => {
    if (following) setIndex(length);
  }, [length, following]);

  useEffect(() => {
    if (!playing) return;
    if (index >= length) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setIndex((i) => Math.min(length, i + 1)), 900 / speed);
    return () => clearTimeout(t);
  }, [playing, index, length, speed]);

  const go = useCallback(
    (i: number) => {
      setFollowing(false);
      setIndex(Math.max(0, Math.min(length, i)));
    },
    [length],
  );
  return { index, setIndex: go, playing, setPlaying, speed, setSpeed, following, setFollowing };
}

export function Timeline({ steps, index, onSeek, markers, compact }: { steps: Step[]; index: number; onSeek: (i: number) => void; markers: Record<MarkerKind, number[]>; compact?: boolean }) {
  const n = Math.max(1, steps.length);
  const markerAt = useMemo(() => {
    const m = new Map<number, MarkerKind>();
    (["outcome", "unlock", "clue", "invalid"] as MarkerKind[]).forEach((k) => markers[k].forEach((i) => !m.has(i) && m.set(i, k)));
    return m;
  }, [markers]);
  return (
    <div className="select-none">
      <div
        className="relative h-9 cursor-pointer"
        role="slider"
        tabIndex={0}
        aria-label="Replay position"
        aria-valuemin={0}
        aria-valuemax={steps.length}
        aria-valuenow={index}
        aria-valuetext={`Step ${index} of ${steps.length}`}
        onClick={(e) => {
          const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
          onSeek(Math.round(((e.clientX - rect.left) / rect.width) * steps.length));
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") onSeek(index + 1);
          if (e.key === "ArrowLeft") onSeek(index - 1);
          if (e.key === "Home") onSeek(0);
          if (e.key === "End") onSeek(steps.length);
        }}
      >
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-sunken" />
        <div className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-ink/70" style={{ width: `${(index / n) * 100}%` }} />
        {steps.map((s, i) => {
          const k = markerAt.get(i + 1);
          if (!k || compact) return null;
          const Icon = MARKER_META[k].icon;
          return (
            <span key={i} className={clsx("absolute top-0 -translate-x-1/2", MARKER_META[k].cls)} style={{ left: `${((i + 1) / n) * 100}%` }} aria-hidden>
              <Icon className="size-3" />
            </span>
          );
        })}
        <div className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-ink shadow" style={{ left: `${(index / n) * 100}%` }} />
      </div>
    </div>
  );
}

export function PlaybackControls({
  pb,
  steps,
  markers,
  showKeys = true,
}: {
  pb: ReturnType<typeof usePlayback>;
  steps: Step[];
  markers: Record<MarkerKind, number[]>;
  showKeys?: boolean;
}) {
  const jump = useCallback(
    (kind: MarkerKind, dir: 1 | -1) => {
      const list = markers[kind];
      const target = dir > 0 ? list.find((i) => i > pb.index) : [...list].reverse().find((i) => i < pb.index);
      if (target !== undefined) pb.setIndex(target);
    },
    [markers, pb],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === " ") {
        e.preventDefault();
        pb.setPlaying(!pb.playing);
      } else if (e.key === "ArrowRight" && !(el?.getAttribute("role") === "slider")) pb.setIndex(pb.index + 1);
      else if (e.key === "ArrowLeft" && !(el?.getAttribute("role") === "slider")) pb.setIndex(pb.index - 1);
      else if (e.key === "c") jump("clue", e.shiftKey ? -1 : 1);
      else if (e.key === "i") jump("invalid", e.shiftKey ? -1 : 1);
      else if (e.key === "u") jump("unlock", e.shiftKey ? -1 : 1);
      else if (e.key === "o") jump("outcome", 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pb, jump]);

  const btn = "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 text-sm text-ink hover:bg-sunken disabled:opacity-40";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button className={btn} onClick={() => pb.setIndex(0)} aria-label="Go to start">
          <SkipBack className="size-4" aria-hidden />
        </button>
        <button className={btn} onClick={() => pb.setIndex(pb.index - 1)} aria-label="Step back" disabled={pb.index <= 0}>
          <ChevronLeft className="size-4" aria-hidden />
        </button>
        <button
          className="inline-flex h-9 min-w-[5.5rem] items-center justify-center gap-1.5 rounded-lg bg-ink px-3 text-sm font-medium text-paper hover:bg-ink-2"
          onClick={() => {
            if (!pb.playing && pb.index >= steps.length) pb.setIndex(0);
            pb.setPlaying(!pb.playing);
          }}
          aria-label={pb.playing ? "Pause" : pb.index >= steps.length ? "Replay from the start" : "Play"}
        >
          {pb.playing ? <Pause className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />}
          {pb.playing ? "Pause" : pb.index >= steps.length && steps.length ? "Replay" : "Play"}
        </button>
        <button className={btn} onClick={() => pb.setIndex(pb.index + 1)} aria-label="Step forward" disabled={pb.index >= steps.length}>
          <ChevronRight className="size-4" aria-hidden />
        </button>
        <button className={btn} onClick={() => pb.setIndex(steps.length)} aria-label="Go to end">
          <SkipForward className="size-4" aria-hidden />
        </button>
        <label className="ml-1 flex items-center gap-2 text-sm text-muted">
          Speed
          <select className="h-9 rounded-lg border border-line bg-surface px-2 text-sm text-ink" value={pb.speed} onChange={(e) => pb.setSpeed(Number(e.target.value))}>
            {[0.5, 1, 2, 4, 8].map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </label>
        <span className="ml-auto font-mono text-sm text-muted tabular">
          step {pb.index} / {steps.length}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs text-muted">Jump to</span>
        {(Object.keys(MARKER_META) as MarkerKind[]).map((k) => {
          const M = MARKER_META[k];
          const count = markers[k].length;
          return (
            <span key={k} className="inline-flex overflow-hidden rounded-lg border border-line">
              <button className="flex h-8 items-center gap-1 px-2 text-xs text-ink hover:bg-sunken disabled:opacity-40" onClick={() => jump(k, -1)} disabled={!count} aria-label={`Previous ${M.label.toLowerCase()}`}>
                <ChevronLeft className="size-3" aria-hidden />
              </button>
              <button className="flex h-8 items-center gap-1.5 border-l border-line px-2 text-xs text-ink hover:bg-sunken disabled:opacity-40" onClick={() => jump(k, 1)} disabled={!count} aria-label={`Next ${M.label.toLowerCase()}`}>
                <M.icon className={clsx("size-3.5", M.cls)} aria-hidden />
                {M.label}
                <span className="text-faint tabular">{count}</span>
              </button>
            </span>
          );
        })}
      </div>
      <Timeline steps={steps} index={pb.index} onSeek={pb.setIndex} markers={markers} />
      {showKeys && (
        <p className="text-xs text-muted">
          Keys: <Kbd>Space</Kbd> play · <Kbd>←</Kbd> <Kbd>→</Kbd> step · <Kbd>c</Kbd> clue · <Kbd>i</Kbd> invalid · <Kbd>u</Kbd> unlock · <Kbd>o</Kbd> outcome (Shift goes back)
        </p>
      )}
    </div>
  );
}
