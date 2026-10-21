"use client";

import clsx from "clsx";
import {
  Archive,
  ArrowRight,
  BookOpen,
  Box,
  CalendarDays,
  CreditCard,
  DoorOpen,
  Eye,
  FileText,
  Hand,
  Hash as HashIcon,
  KeyRound,
  Lightbulb,
  Lock,
  Monitor,
  Package,
  Power,
  RotateCcw,
  ScanLine,
  ShieldCheck,
  StickyNote,
  Terminal,
  Wrench,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BudgetMeter, EventChips, ResultLine, StateChips } from "@/components/observation";
import { Badge, Button, ButtonLink, Card, Dialog, Kbd, Notice, OutcomeBadge, Page, PageHeader, Spinner } from "@/components/ui";
import { ApiError, api, newActionId } from "@/lib/api";
import { actionText } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Action, Obj, Observation, Replay, Result, RoomMeta } from "@/lib/types";

type Live = {
  runId: string;
  token: string;
  room: RoomMeta;
  seq: number;
  hash: string;
  status: string;
  obs: Observation;
  certificateId: string | null;
};

type LogEntry = { seq: number; action: Action; result: Result };

const STORE = "esc-play-run";

function objectIcon(id: string) {
  const cls = "size-5";
  if (/panel|fuse/.test(id)) return <Zap className={cls} aria-hidden />;
  if (/screwdriver|vice/.test(id)) return <Wrench className={cls} aria-hidden />;
  if (/cabinet|drawer|crate|locker|bin|box/.test(id)) return <Archive className={cls} aria-hidden />;
  if (/note|roster|chart|calendar|board|poster/.test(id)) return <FileText className={cls} aria-hidden />;
  if (/terminal|monitor/.test(id)) return <Monitor className={cls} aria-hidden />;
  if (/card/.test(id)) return <CreditCard className={cls} aria-hidden />;
  if (/reader/.test(id)) return <ScanLine className={cls} aria-hidden />;
  return <Box className={cls} aria-hidden />;
}

function parseCommand(line: string): { tool: string; arguments: Record<string, string> } | string | null {
  const p = line.trim().split(/\s+/).filter(Boolean);
  if (!p.length) return null;
  const [v, ...a] = p;
  const verb = v.toLowerCase();
  if (["inspect", "look", "x"].includes(verb) && a.length === 1) return { tool: "inspect", arguments: { target_id: a[0] } };
  if (["take", "get"].includes(verb) && a.length === 1) return { tool: "take", arguments: { item_id: a[0] } };
  if (verb === "use" && a.length === 2) return { tool: "use", arguments: { item_id: a[0], target_id: a[1] } };
  if (verb === "use" && a.length === 3 && ["on", "with"].includes(a[1])) return { tool: "use", arguments: { item_id: a[0], target_id: a[2] } };
  if (["open", "close", "activate"].includes(verb) && a.length === 1) return { tool: "interact", arguments: { target_id: a[0], operation: verb } };
  if (["code", "enter"].includes(verb) && a.length === 2) return { tool: "interact", arguments: { target_id: a[0], operation: "enter_code", value: a[1] } };
  if (["move", "go"].includes(verb) && a.length === 1) return { tool: "move", arguments: { destination_id: a[0] } };
  if (["journal", "j", "review_journal"].includes(verb)) return { tool: "review_journal", arguments: {} };
  return `Not a command: “${line.trim()}”. Try: inspect maintenance_panel · take screwdriver · use screwdriver on maintenance_panel · open tool_cabinet · code equipment_locker 123 · move control_room · journal`;
}

function RoomPicker({ onStart, busy, error }: { onStart: (room: "practice" | "daily") => void; busy: string | null; error: string | null }) {
  const { user } = useMe();
  return (
    <Page>
      <PageHeader
        eyebrow="Play"
        title="Try the room yourself"
        lede="Humans and agents use exactly the same six actions and see the same information. The emergency clock advances when you take an action, not while you read."
      />
      {error && <Notice tone="bad" className="mb-6">{error}</Notice>}
      <div className="grid gap-5 md:grid-cols-2">
        <Card className="flex flex-col p-6">
          <div className="flex items-center justify-between">
            <Badge tone="good" icon={<ShieldCheck className="size-3" aria-hidden />}>Open to everyone</Badge>
            <span className="text-sm text-muted">Unranked</span>
          </div>
          <h2 className="mt-4 font-serif text-3xl text-ink">Practice</h2>
          <p className="mt-2 text-ink-2">
            A research station has entered emergency lockdown. Restore power, find an access card and decode a terminal credential. One fixed public room, three locations, 60 actions.
          </p>
          <ul className="mt-4 space-y-1.5 text-sm text-muted">
            <li>· No sign-in needed. Sign in to get a certificate for your run.</li>
            <li>· Optional progressive hints, recorded on the run.</li>
          </ul>
          <div className="mt-auto pt-6">
            <Button variant="primary" size="lg" onClick={() => onStart("practice")} loading={busy === "practice"} icon={<ArrowRight className="size-4" aria-hidden />}>
              Start Practice
            </Button>
          </div>
        </Card>
        <Card className="flex flex-col p-6">
          <div className="flex items-center justify-between">
            <Badge tone="signal" icon={<CalendarDays className="size-3" aria-hidden />}>Today, UTC</Badge>
            <span className="text-sm text-muted">3 attempts</span>
          </div>
          <h2 className="mt-4 font-serif text-3xl text-ink">Daily Room</h2>
          <p className="mt-2 text-ink-2">
            One Standard-tier room from today&apos;s seed, the same for everyone. Humans and agents have separate boards. Results and the solution unlock after the UTC day ends.
          </p>
          <ul className="mt-4 space-y-1.5 text-sm text-muted">
            <li>· Hinted runs are excluded from the unassisted board.</li>
            <li>· Codes have four digits and need two facts combined.</li>
          </ul>
          <div className="mt-auto pt-6">
            {user ? (
              <Button variant="secondary" size="lg" onClick={() => onStart("daily")} loading={busy === "daily"} icon={<ArrowRight className="size-4" aria-hidden />}>
                Start today&apos;s room
              </Button>
            ) : (
              <ButtonLink href="/signin?next=/play" size="lg">Sign in to play the Daily Room</ButtonLink>
            )}
          </div>
        </Card>
      </div>
      <Card className="mt-6 p-6">
        <h2 className="font-semibold text-ink">How to play</h2>
        <div className="mt-3 grid gap-4 text-sm text-ink-2 sm:grid-cols-3">
          <p><span className="font-medium text-ink">Select an object</span> to see what you can do with it. Inspecting, taking and opening each cost one action, and so does a failed attempt.</p>
          <p><span className="font-medium text-ink">Select an item you carry</span>, then an object, to use one on the other. Codes come from facts you discover; after three wrong codes at one lock, each further try costs two extra actions.</p>
          <p><span className="font-medium text-ink">Prefer the keyboard?</span> Press <Kbd>/</Kbd> and type commands like <code className="font-mono">open tool_cabinet</code>. Everything is reachable with <Kbd>Tab</Kbd>.</p>
        </div>
      </Card>
    </Page>
  );
}

function PlayInner() {
  const params = useSearchParams();
  const { user } = useMe();
  const [live, setLive] = useState<Live | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [item, setItem] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [cmd, setCmd] = useState("");
  const [cmdError, setCmdError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [histIdx, setHistIdx] = useState(-1);
  const [notes, setNotes] = useState("");
  const [hintOpen, setHintOpen] = useState(false);
  const [hints, setHints] = useState<{ hint: string; level: number; levels: number }[]>([]);
  const [restartOpen, setRestartOpen] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const cmdRef = useRef<HTMLInputElement>(null);
  const logEnd = useRef<HTMLDivElement>(null);

  // Resume a run after a refresh with its token.
  useEffect(() => {
    const raw = sessionStorage.getItem(STORE);
    if (!raw) {
      setRestoring(false);
      return;
    }
    const saved = JSON.parse(raw) as { runId: string; token: string; room: RoomMeta };
    (async () => {
      try {
        const o = await api<{ sequence: number; chain_hash: string; status: string; observation: Observation; certificate_id: string | null }>(`/api/v1/runs/${saved.runId}/observation`, { runToken: saved.token });
        const r = await api<{ replay: Replay }>(`/api/v1/runs/${saved.runId}/replay`, { runToken: saved.token });
        setLog(r.replay.steps.filter((s) => !s.system).map((s) => ({ seq: s.seq, action: s.action, result: s.result })));
        setLive({ runId: saved.runId, token: saved.token, room: saved.room, seq: o.sequence, hash: o.chain_hash, status: o.status, obs: o.observation, certificateId: o.certificate_id });
        try {
          setNotes(localStorage.getItem(`esc-notes-${saved.runId}`) ?? "");
        } catch {}
      } catch {
        sessionStorage.removeItem(STORE);
      } finally {
        setRestoring(false);
      }
    })();
  }, []);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ block: "nearest" });
  }, [log.length]);

  useEffect(() => {
    if (!live) return;
    try {
      localStorage.setItem(`esc-notes-${live.runId}`, notes);
    } catch {}
  }, [notes, live]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && t.tagName !== "INPUT" && t.tagName !== "TEXTAREA") {
        e.preventDefault();
        cmdRef.current?.focus();
      }
      if (e.key === "Escape") {
        setSelected(null);
        setItem(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const start = useCallback(async (room: "practice" | "daily", replace = false) => {
    setBusy(room);
    setError(null);
    try {
      const d = await api<{ run_id: string; run_token: string; room: RoomMeta; sequence: number; chain_hash: string; status: string; observation: Observation }>("/api/v1/runs", {
        body: { room, agent_type: "human", replace_active: replace },
      });
      sessionStorage.setItem(STORE, JSON.stringify({ runId: d.run_id, token: d.run_token, room: d.room }));
      setLive({ runId: d.run_id, token: d.run_token, room: d.room, seq: d.sequence, hash: d.chain_hash, status: d.status, obs: d.observation, certificateId: null });
      setLog([]);
      setHints([]);
      setNotes("");
      setSelected(null);
      setItem(null);
    } catch (e) {
      if (e instanceof ApiError && e.code === "ACTIVE_RUN_EXISTS") {
        await start(room, true);
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    const room = params.get("room");
    if (!restoring && !live && (room === "practice" || room === "daily")) start(room);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restoring]);

  const send = useCallback(
    async (tool: string, args: Record<string, string>) => {
      if (!live || pending || live.status !== "in_progress") return;
      setPending(true);
      setError(null);
      try {
        const d = await api<{ sequence: number; result: Result; observation: Observation; chain_hash: string; status: string; certificate_id: string | null }>(`/api/v1/runs/${live.runId}/actions`, {
          runToken: live.token,
          body: { expected_sequence: live.seq + 1, action_id: newActionId(), prev_hash: live.hash, tool, arguments: args },
        });
        setLog((l) => [...l, { seq: d.sequence, action: { tool, arguments: args }, result: d.result }]);
        setLive((x) => (x ? { ...x, seq: d.sequence, hash: d.chain_hash, status: d.status, obs: d.observation, certificateId: d.certificate_id } : x));
        if (tool === "take" && d.result.ok) setSelected(null);
        if (tool === "use" && d.result.ok) setItem(null);
        if (tool === "interact" && args.operation === "enter_code") setCode("");
      } catch (e) {
        if (e instanceof ApiError && (e.code === "STALE_SEQUENCE" || e.code === "CHAIN_MISMATCH")) {
          const o = await api<{ sequence: number; chain_hash: string; status: string; observation: Observation }>(`/api/v1/runs/${live.runId}/observation`, { runToken: live.token });
          setLive((x) => (x ? { ...x, seq: o.sequence, hash: o.chain_hash, status: o.status, obs: o.observation } : x));
          setError("Your view was out of date and has been refreshed. Try that again.");
        } else if (e instanceof ApiError && e.code === "EPISODE_FINISHED") {
          setLive((x) => (x ? { ...x, status: String(e.details.status ?? "client_aborted"), certificateId: (e.details.certificate_id as string) ?? x.certificateId } : x));
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        setPending(false);
      }
    },
    [live, pending],
  );

  const finishAndClear = useCallback(async () => {
    if (live && live.status === "in_progress") {
      try {
        await api(`/api/v1/runs/${live.runId}/finish`, { runToken: live.token, body: {} });
      } catch {}
    }
    sessionStorage.removeItem(STORE);
  }, [live]);

  const takeHint = useCallback(async () => {
    if (!live) return;
    try {
      const h = await api<{ hint: string; level: number; levels: number }>(`/api/v1/runs/${live.runId}/hint`, { runToken: live.token, body: { confirm: true } });
      setHints((x) => [...x, h]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setHintOpen(false);
    }
  }, [live]);

  const clues = useMemo(() => {
    const out = new Map<string, string>();
    for (const e of log) {
      for (const ev of e.result.events ?? []) if (ev.type === "clue_discovered") out.set(ev.clue_id, e.result.message);
      for (const c of e.result.data?.clues ?? []) out.set(c.id, c.text);
    }
    return [...out.entries()];
  }, [log]);

  if (restoring) return <Page><Spinner label="Restoring your run" /></Page>;
  if (!live) return <RoomPicker onStart={(r) => start(r)} busy={busy} error={error} />;

  const obs = live.obs;
  const done = live.status !== "in_progress";
  const sel: Obj | undefined = obs.objects.find((o) => o.id === selected) ?? undefined;
  const selInv = obs.inventory.find((i) => i.id === selected);
  const last = log[log.length - 1];

  const submitCmd = (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = parseCommand(cmd);
    if (!parsed) return;
    if (typeof parsed === "string") {
      setCmdError(parsed);
      return;
    }
    setCmdError(null);
    setHistory((h) => [cmd, ...h].slice(0, 50));
    setHistIdx(-1);
    setCmd("");
    send(parsed.tool, parsed.arguments);
  };

  return (
    <main className="mx-auto w-full max-w-[1400px] animate-in px-4 pb-24 pt-6 sm:px-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[13px] font-medium uppercase tracking-[0.12em] text-muted">{live.room.kind === "daily" ? "Daily Room" : "Practice"} · {live.room.tier} tier</div>
          <h1 className="font-serif text-3xl text-ink">{live.room.title}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {hints.length > 0 && <Badge tone="warn" icon={<Lightbulb className="size-3" aria-hidden />}>Assisted · {hints.length} hint{hints.length > 1 ? "s" : ""}</Badge>}
          {!done && (
            <Button size="sm" variant="ghost" icon={<Lightbulb className="size-4" aria-hidden />} onClick={() => setHintOpen(true)}>
              Hint
            </Button>
          )}
          <Button size="sm" variant="ghost" icon={<RotateCcw className="size-4" aria-hidden />} onClick={() => setRestartOpen(true)}>
            Restart
          </Button>
          <Link href={`/runs/${live.runId}`} className="text-sm text-muted underline-offset-2 hover:text-ink hover:underline">
            Watch link
          </Link>
        </div>
      </div>

      {done && (
        <Card className="mb-6 overflow-hidden">
          <div className={clsx("flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between", live.status === "escaped" ? "bg-good-soft" : "bg-sunken")}>
            <div>
              <OutcomeBadge status={live.status} size="lg" />
              <h2 className="mt-3 font-serif text-3xl text-ink">{live.status === "escaped" ? "You escaped." : "The run has ended."}</h2>
              <p className="mt-1 text-ink-2">
                {obs.actions_used} of {obs.action_budget} actions used{hints.length ? `, with ${hints.length} hint${hints.length > 1 ? "s" : ""}` : ", unassisted"}.
                {!user && " Sign in next time to receive a signed certificate."}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <ButtonLink href={`/runs/${live.runId}`} variant="primary" icon={<Eye className="size-4" aria-hidden />}>Watch the replay</ButtonLink>
              {live.certificateId && <ButtonLink href={`/c/${live.certificateId}`} icon={<ShieldCheck className="size-4" aria-hidden />}>Certificate</ButtonLink>}
              {user && <ButtonLink href={`/runs/${live.runId}/clinic`}>Trace Clinic</ButtonLink>}
              <Button
                onClick={async () => {
                  await finishAndClear();
                  setLive(null);
                }}
                icon={<RotateCcw className="size-4" aria-hidden />}
              >
                Play again
              </Button>
            </div>
          </div>
        </Card>
      )}

      {error && <Notice tone="bad" className="mb-4">{error}</Notice>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-5">
          <Card className="p-5 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <div className="text-[13px] font-medium uppercase tracking-wider text-muted">You are in</div>
                <h2 className="mt-1 font-serif text-[1.9rem] leading-tight text-ink">{obs.location.name}</h2>
                <p className="mt-2 text-ink-2">{obs.location.description}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {obs.exits.map((e) => (
                  <Button key={e.id} size="sm" disabled={done || pending} onClick={() => send("move", { destination_id: e.id })} icon={<DoorOpen className="size-4" aria-hidden />}>
                    {e.name}
                  </Button>
                ))}
              </div>
            </div>
            {last && (
              <div aria-live="polite" className="mt-5">
                <ResultLine action={last.action} result={last.result} seq={last.seq} />
              </div>
            )}
          </Card>

          <section aria-labelledby="objects-h">
            <div className="mb-3 flex items-baseline justify-between">
              <h3 id="objects-h" className="text-sm font-semibold text-ink">What you can see</h3>
              {item && <span className="text-sm text-signal-ink">Using {obs.inventory.find((i) => i.id === item)?.name}: choose a target</span>}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {obs.objects.map((o) => (
                <button
                  key={o.id}
                  onClick={() => setSelected(selected === o.id ? null : o.id)}
                  aria-pressed={selected === o.id}
                  className={clsx(
                    "group flex items-start gap-3 rounded-xl border bg-surface p-3.5 text-left transition-all",
                    selected === o.id ? "border-ink ring-2 ring-ink/10" : "border-line hover:border-line-strong hover:shadow-card",
                  )}
                >
                  <span className={clsx("grid size-10 shrink-0 place-items-center rounded-lg", selected === o.id ? "bg-ink text-paper" : "bg-sunken text-ink-2")}>{objectIcon(o.id)}</span>
                  <span className="min-w-0">
                    <span className="block font-medium text-ink">{o.name}</span>
                    <code className="block font-mono text-[11.5px] text-faint">{o.id}</code>
                    <span className="mt-1.5 flex flex-wrap gap-1">
                      <StateChips state={o.state} />
                      {o.in && <Badge>in {o.in.replaceAll("_", " ")}</Badge>}
                      {o.portable && <Badge icon={<Package className="size-3" aria-hidden />}>portable</Badge>}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </section>

          {(sel || selInv) && !done && (
            <Card className="animate-in border-ink/20 p-4" aria-live="polite">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mr-2 text-sm text-muted">
                  {sel ? sel.name : selInv?.name}
                  {selInv && " (carried)"}
                </span>
                <Button size="sm" variant="primary" disabled={pending} onClick={() => send("inspect", { target_id: (sel?.id ?? selInv?.id)! })} icon={<Eye className="size-4" aria-hidden />}>
                  Inspect
                </Button>
                {sel?.portable && (
                  <Button size="sm" disabled={pending} onClick={() => send("take", { item_id: sel.id })} icon={<Hand className="size-4" aria-hidden />}>
                    Take
                  </Button>
                )}
                {sel?.operations?.filter((op) => op !== "enter_code").map((op) => (
                  <Button key={op} size="sm" disabled={pending} onClick={() => send("interact", { target_id: sel.id, operation: op })} icon={op === "activate" ? <Power className="size-4" aria-hidden /> : op === "open" ? <Archive className="size-4" aria-hidden /> : <Lock className="size-4" aria-hidden />}>
                    {op.charAt(0).toUpperCase() + op.slice(1)}
                  </Button>
                ))}
                {sel?.operations?.includes("enter_code") && (
                  <form
                    className="flex items-center gap-1.5"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (/^\d{1,12}$/.test(code)) send("interact", { target_id: sel.id, operation: "enter_code", value: code });
                    }}
                  >
                    <label className="sr-only" htmlFor="code-input">Code</label>
                    <input
                      id="code-input"
                      inputMode="numeric"
                      autoComplete="off"
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 12))}
                      placeholder="Code"
                      className="h-8 w-24 rounded-lg border border-line-strong bg-surface px-2.5 font-mono text-sm text-ink"
                    />
                    <Button size="sm" type="submit" disabled={pending || !code} icon={<KeyRound className="size-4" aria-hidden />}>
                      Enter code
                    </Button>
                  </form>
                )}
                {item && sel && item !== sel.id && (
                  <Button size="sm" variant="signal" disabled={pending} onClick={() => send("use", { item_id: item, target_id: sel.id })} icon={<Wrench className="size-4" aria-hidden />}>
                    Use {obs.inventory.find((i) => i.id === item)?.name} on {sel.name}
                  </Button>
                )}
              </div>
            </Card>
          )}

          <section aria-labelledby="inv-h">
            <h3 id="inv-h" className="mb-3 text-sm font-semibold text-ink">You are carrying</h3>
            {obs.inventory.length ? (
              <div className="flex flex-wrap gap-2">
                {obs.inventory.map((i) => (
                  <span key={i.id} className="inline-flex overflow-hidden rounded-xl border border-line bg-surface">
                    <button
                      onClick={() => setItem(item === i.id ? null : i.id)}
                      aria-pressed={item === i.id}
                      className={clsx("flex items-center gap-2 px-3 py-2 text-sm", item === i.id ? "bg-signal-soft text-signal-ink" : "text-ink hover:bg-sunken")}
                    >
                      {objectIcon(i.id)}
                      {item === i.id ? `Using ${i.name}` : `Use ${i.name}…`}
                    </button>
                    <button onClick={() => send("inspect", { target_id: i.id })} disabled={done || pending} className="border-l border-line px-2.5 text-muted hover:bg-sunken hover:text-ink disabled:opacity-40" aria-label={`Inspect ${i.name} (1 action)`} title="Inspect (1 action)">
                      <Eye className="size-4" aria-hidden />
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">Nothing yet.</p>
            )}
          </section>

          <form onSubmit={submitCmd} className="rounded-xl border border-line bg-surface p-2">
            <label htmlFor="cmd" className="sr-only">Command</label>
            <div className="flex items-center gap-2">
              <Terminal className="ml-2 size-4 text-faint" aria-hidden />
              <input
                id="cmd"
                ref={cmdRef}
                value={cmd}
                disabled={done}
                onChange={(e) => setCmd(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowUp" && history.length) {
                    e.preventDefault();
                    const n = Math.min(history.length - 1, histIdx + 1);
                    setHistIdx(n);
                    setCmd(history[n]);
                  }
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    const n = histIdx - 1;
                    setHistIdx(Math.max(-1, n));
                    setCmd(n >= 0 ? history[n] : "");
                  }
                }}
                placeholder="Type a command, e.g. open tool_cabinet    (press / to focus)"
                className="h-10 min-w-0 flex-1 bg-transparent font-mono text-sm text-ink placeholder:text-faint focus:outline-none"
                autoComplete="off"
                spellCheck={false}
              />
              <Button size="sm" type="submit" disabled={done || pending || !cmd.trim()}>Run</Button>
            </div>
            {cmdError && <p className="px-2 pb-1 pt-2 text-sm text-bad">{cmdError}</p>}
          </form>
        </div>

        <aside className="space-y-5">
          <Card className="p-5">
            <BudgetMeter obs={obs} />
            <p className="mt-3 text-[13px] leading-relaxed text-muted">Goal: {obs.goal} The clock advances when you act, not while you read.</p>
          </Card>

          <Card>
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <BookOpen className="size-4" aria-hidden /> Journal
              </h3>
              <Button size="sm" variant="ghost" disabled={done || pending} onClick={() => send("review_journal", {})} title="Costs one action, as it does for agents">
                Review (1 action)
              </Button>
            </div>
            <div className="max-h-72 overflow-y-auto px-5 py-3">
              {clues.length ? (
                <ul className="space-y-2.5">
                  {clues.map(([id, text]) => (
                    <li key={id} className="text-sm">
                      <code className="font-mono text-xs text-signal-ink">{id}</code>
                      <p className="mt-0.5 text-ink-2">{text}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">Clues you discover will appear here with stable ids, like clue_07.</p>
              )}
            </div>
          </Card>

          {hints.length > 0 && (
            <Card className="p-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-ink"><Lightbulb className="size-4 text-warn" aria-hidden /> Hints taken</h3>
              <ul className="mt-2 space-y-2 text-sm text-ink-2">
                {hints.map((h, i) => (
                  <li key={i}>
                    <span className="text-xs text-muted">Level {h.level} of {h.levels}</span>
                    <p>{h.hint}</p>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card className="p-5">
            <label htmlFor="notes" className="flex items-center gap-2 text-sm font-semibold text-ink">
              <StickyNote className="size-4" aria-hidden /> Your notes
            </label>
            <p className="mt-0.5 text-xs text-muted">Private to this browser. Notes never change the world.</p>
            <textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              className="mt-2 w-full resize-y rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink placeholder:text-faint"
              placeholder="Label digits, offsets, ideas…"
            />
          </Card>

          <Card>
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <HashIcon className="size-4" aria-hidden /> Log
              </h3>
              <span className="font-mono text-xs text-faint">{log.length} actions</span>
            </div>
            <ol className="max-h-80 space-y-2 overflow-y-auto px-5 py-3">
              {log.length === 0 && <li className="text-sm text-muted">Every action you take is recorded and hash-chained.</li>}
              {log.map((e) => (
                <li key={e.seq} className="text-[13px]">
                  <div className="flex items-start gap-2">
                    <span className="font-mono text-faint tabular">{String(e.seq).padStart(2, "0")}</span>
                    <div className="min-w-0">
                      <code className={clsx("font-mono", e.result.ok ? "text-ink" : "text-bad")}>{actionText(e.action)}</code>
                      <p className="text-muted">{e.result.message}</p>
                      <EventChips events={e.result.events} />
                    </div>
                  </div>
                </li>
              ))}
              <div ref={logEnd} />
            </ol>
          </Card>
        </aside>
      </div>

      <Dialog
        open={hintOpen}
        onClose={() => setHintOpen(false)}
        title="Take a hint?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setHintOpen(false)}>Keep trying</Button>
            <Button variant="primary" onClick={takeHint} icon={<Lightbulb className="size-4" aria-hidden />}>Show a hint</Button>
          </>
        }
      >
        <p>Hints are progressive: the first one nudges, the next one tells you more. Taking any hint marks this run as assisted, and assisted runs are left off the unassisted Daily board.</p>
        <p className="mt-2">Hints are never shown to agents.</p>
      </Dialog>

      <Dialog
        open={restartOpen}
        onClose={() => setRestartOpen(false)}
        title="Restart this room?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setRestartOpen(false)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={async () => {
                setRestartOpen(false);
                const room = live.room.kind === "daily" ? "daily" : "practice";
                await finishAndClear();
                setLive(null);
                await start(room, true);
              }}
            >
              End and restart
            </Button>
          </>
        }
      >
        <p>The current run ends as “ended by client” and stays in your history: failures are never deleted. {live.room.kind === "daily" && "A Daily restart uses one of your three attempts."}</p>
      </Dialog>
    </main>
  );
}

export default function PlayPage() {
  return (
    <Suspense fallback={<Page><Spinner /></Page>}>
      <PlayInner />
    </Suspense>
  );
}
