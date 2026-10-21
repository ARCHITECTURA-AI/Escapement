"use client";

import { Download, Eye, EyeOff, FileCheck2, Lock, Radio, Share2, Stethoscope } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { EventChips, ObservationPanel, ResultLine } from "@/components/observation";
import { PlaybackControls, markersFor, observationAt, usePlayback } from "@/components/replay-player";
import { Badge, Button, ButtonLink, Card, CardHeader, ErrorState, Hash, KV, Notice, OutcomeBadge, Page, Skeleton, Source } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { actionText, dateTime, duration, titleCase, usd } from "@/lib/format";
import type { Replay, RunSummary, Step } from "@/lib/types";

type Solution = { solution: { tool: string; arguments: Record<string, string> }[]; min_length: number; optimality: string; optimality_label: string; milestones: { id: string; label: string }[]; path_efficiency: number | null };

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [embargo, setEmbargo] = useState<string | null>(null);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [showSolution, setShowSolution] = useState(false);
  const [shared, setShared] = useState(false);
  const viewed = useRef(false);

  const token = typeof window !== "undefined" ? (() => {
    try {
      const raw = sessionStorage.getItem("esc-play-run");
      const saved = raw ? (JSON.parse(raw) as { runId: string; token: string }) : null;
      return saved?.runId === id ? saved.token : undefined;
    } catch {
      return undefined;
    }
  })() : undefined;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api<{ run: RunSummary; replay: Replay }>(`/api/v1/runs/${id}/replay`, { runToken: token });
        if (cancelled) return;
        setSummary(r.run);
        setReplay(r.replay);
        if (!viewed.current) {
          viewed.current = true;
          api(`/api/v1/runs/${id}/events`, { body: { type: "view" } }).catch(() => {});
        }
      } catch (e) {
        if (e instanceof ApiError && e.code === "EMBARGOED") {
          setEmbargo(String(e.details.embargo_until ?? ""));
          try {
            setSummary(await api<RunSummary>(`/api/v1/runs/${id}`));
          } catch {}
        } else setError(e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, token]);

  // Live: follow new steps while the run is in progress.
  const live = summary?.status === "in_progress";
  useEffect(() => {
    if (!live || !replay) return;
    const t = setInterval(async () => {
      try {
        const last = replay.steps.length ? replay.steps[replay.steps.length - 1].seq : 0;
        const r = await api<{ run: RunSummary; steps: Step[]; status: string }>(`/api/v1/runs/${id}/replay?after_seq=${last}`, { runToken: token });
        if (r.steps.length) setReplay((x) => (x ? { ...x, steps: [...x.steps, ...r.steps], outcome: r.status } : x));
        setSummary(r.run);
      } catch {}
    }, 1200);
    return () => clearInterval(t);
  }, [live, replay, id, token]);

  useEffect(() => {
    if (!summary || summary.status === "in_progress" || !summary.room.manifest_public) return;
    api<Solution>(`/api/v1/runs/${id}/solution`).then(setSolution).catch(() => setSolution(null));
  }, [summary, id]);

  const steps = replay?.steps ?? [];
  const pb = usePlayback(steps.length, { follow: true });
  const markers = useMemo(() => markersFor(steps), [steps]);
  const seeked = useRef(false);
  useEffect(() => {
    if (seeked.current || !steps.length) return;
    const m = /^#step-(\d+)$/.exec(window.location.hash);
    if (m) {
      seeked.current = true;
      pb.setIndex(Number(m[1]));
    }
  }, [steps.length, pb]);

  if (error) return <Page><ErrorState error={error} /></Page>;
  if (!summary) return <Page><Skeleton className="h-10 w-80" /><Skeleton className="mt-6 h-[480px]" /></Page>;

  const agent = summary.agent;
  const isHuman = summary.agent_type === "human";
  const attested = Boolean(agent.model_attested);
  const step = pb.index > 0 ? steps[pb.index - 1] : null;
  const obs = replay ? observationAt(replay.initial_observation, steps, pb.index) : null;

  const share = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) await navigator.share({ title: "Escapement run", url });
      else await navigator.clipboard.writeText(url);
      setShared(true);
      api(`/api/v1/runs/${id}/events`, { body: { type: "share" } }).catch(() => {});
    } catch {}
  };

  return (
    <main className="mx-auto w-full max-w-[1400px] animate-in px-4 pb-24 pt-8 sm:px-6">
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
            <span className="font-medium uppercase tracking-[0.12em]">Watch</span>
            <span>·</span>
            <Link href={`/rooms/${summary.room.id}`} className="hover:text-ink">{summary.room.title}</Link>
            <span>·</span>
            <span>{titleCase(summary.mode)}</span>
          </div>
          <h1 className="mt-2 font-serif text-[2.1rem] leading-tight text-ink sm:text-[2.6rem]">
            {isHuman ? "Human player" : agent.name}
            {agent.version && <span className="text-muted"> {agent.version}</span>}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <OutcomeBadge status={summary.status} size="lg" />
            {live && <Badge tone="signal" icon={<Radio className="size-3" aria-hidden />}>Live</Badge>}
            {summary.assisted && <Badge tone="warn">Assisted ({summary.hints_used} hints)</Badge>}
            {agent.model && <span className="text-sm text-ink-2">{agent.model}</span>}
            {agent.model && <Source kind={attested ? "attested" : "self"} />}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {summary.certificate_id && <ButtonLink href={`/c/${summary.certificate_id}`} variant="primary" icon={<FileCheck2 className="size-4" aria-hidden />}>Certificate</ButtonLink>}
          {summary.is_owner && summary.status !== "in_progress" && <ButtonLink href={`/runs/${id}/clinic`} icon={<Stethoscope className="size-4" aria-hidden />}>Trace Clinic</ButtonLink>}
          {replay && (
            <Button onClick={share} icon={<Share2 className="size-4" aria-hidden />}>{shared ? "Link copied" : "Share"}</Button>
          )}
          {replay && (
            <ButtonLink href={`/api/v1/runs/${id}/replay?download=true`} external icon={<Download className="size-4" aria-hidden />}>Replay JSON</ButtonLink>
          )}
        </div>
      </div>

      {embargo !== null && (
        <Notice tone="signal" icon={<Lock className="size-4" aria-hidden />} title="This replay is embargoed" className="mb-6">
          Ranked replays are visible only to their owner until the season closes, and Daily replays until the UTC day ends{embargo ? ` (${dateTime(embargo)})` : ""}. The outcome and certificate are public now.
        </Notice>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-5">
          {replay && obs ? (
            <>
              <Card className="p-5">
                <PlaybackControls pb={pb} steps={steps} markers={markers} />
              </Card>
              <div className="grid gap-5 lg:grid-cols-2">
                <Card>
                  <CardHeader title={pb.index === 0 ? "Initial observation" : `Observation after step ${pb.index}`} subtitle="Exactly what the agent saw. No inner monologue is ever invented." />
                  <div className="p-5">
                    <ObservationPanel obs={obs} />
                  </div>
                </Card>
                <div className="space-y-4">
                  {step ? (
                    <>
                      <div>
                        <div className="mb-2 text-[13px] font-medium uppercase tracking-wider text-muted">Tool call and result</div>
                        <ResultLine action={step.action} result={step.result} seq={step.seq} summary={step.decision_summary} />
                      </div>
                      <Card className="p-4 text-sm">
                        <dl>
                          <KV k="Chain hash" v={<Hash value={step.chain_hash} />} />
                          <KV k="State hash" v={<Hash value={step.state_hash} />} />
                          <KV k="Remaining budget" v={<span className="tabular">{step.observation.actions_remaining} of {step.observation.action_budget}</span>} source="server" />
                          {step.usage && (
                            <KV
                              k="Usage this step"
                              v={<span className="tabular">{[step.usage.tokens_in != null && `${step.usage.tokens_in} in`, step.usage.tokens_out != null && `${step.usage.tokens_out} out`].filter(Boolean).join(" · ") || "—"}</span>}
                              source={attested ? "attested" : "self"}
                            />
                          )}
                          {step.elapsed_ms != null && <KV k="Time since previous" v={duration(step.elapsed_ms)} source="server" />}
                        </dl>
                      </Card>
                    </>
                  ) : (
                    <Notice title="The start of the run">
                      {replay.initial_observation.goal} Press <span className="font-medium">Play</span> or step forward to follow each action.
                    </Notice>
                  )}
                  <Card>
                    <CardHeader title="Action timeline" subtitle={`${steps.length} recorded entries, failures included`} />
                    <ol className="max-h-[420px] overflow-y-auto p-2">
                      {steps.map((s, i) => (
                        <li key={s.seq}>
                          <button
                            onClick={() => pb.setIndex(i + 1)}
                            className={`flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-[13px] ${pb.index === i + 1 ? "bg-sunken" : "hover:bg-sunken/60"}`}
                            aria-current={pb.index === i + 1 ? "step" : undefined}
                          >
                            <span className="w-7 shrink-0 font-mono text-faint tabular">{s.seq}</span>
                            <span className="min-w-0">
                              <code className={`font-mono ${s.result.ok ? "text-ink" : "text-bad"}`}>{actionText(s.action)}</code>
                              <span className="ml-2"><EventChips events={s.result.events.filter((e) => e.type !== "moved" && e.type !== "object_revealed")} /></span>
                            </span>
                          </button>
                        </li>
                      ))}
                    </ol>
                  </Card>
                </div>
              </div>
            </>
          ) : (
            embargo === null && <Skeleton className="h-[480px]" />
          )}
        </div>

        <aside className="space-y-5">
          <Card>
            <CardHeader title="Run facts" subtitle="Measured by the Escapement server" actions={<Source kind="server" />} />
            <dl className="px-5 py-1">
              <KV stack k="Outcome" v={<OutcomeBadge status={summary.status} />} />
              <div className="grid grid-cols-2 gap-x-4">
                <KV stack k="Actions used" v={<span className="tabular">{summary.actions_used} / {summary.action_budget}</span>} />
                <KV stack k="Malformed requests" v={<span className="tabular">{summary.malformed_count}</span>} />
                <KV stack k="Wall time" v={duration(summary.wall_time_ms)} />
                <KV stack k="Engine" v={<span className="font-mono text-[13px]">{summary.engine_version}</span>} />
              </div>
              <KV stack k="Room instance" v={<Hash value={summary.room.instance_hash} />} />
              <KV stack k="Final chain hash" v={<Hash value={summary.final_chain_hash ?? summary.chain_hash} />} />
              <KV stack k="Started" v={dateTime(summary.started_at)} />
            </dl>
          </Card>
          {!isHuman && (
            <Card>
              <CardHeader
                title="Agent configuration"
                subtitle={attested ? "First-party reference run: Escapement ran this model." : "Declared by the client. Escapement cannot verify who or what chose the actions."}
                actions={<Source kind={attested ? "attested" : "self"} />}
              />
              <dl className="px-5 py-1">
                <KV stack k="Agent" v={`${agent.name ?? "—"} ${agent.version ?? ""}`} />
                <KV stack k="Model" v={agent.model ?? "—"} />
                {agent.provider && <KV stack k="Provider" v={agent.provider} />}
                <KV stack k="Framework" v={agent.framework ?? "—"} />
                <KV stack k="Memory strategy" v={agent.memory ?? "—"} />
                <div className="grid grid-cols-2 gap-x-4">
                  <KV stack k="Tokens" v={summary.usage?.tokens_in != null ? `${summary.usage.tokens_in ?? 0} in · ${summary.usage.tokens_out ?? 0} out` : "not reported"} />
                  <KV stack k="Cost" v={usd(summary.usage?.cost_usd_micros)} source={attested ? "self" : undefined} />
                </div>
              </dl>
            </Card>
          )}
          {solution && (
            <Card>
              <CardHeader
                title="Solution view"
                subtitle="Shown after the run ends, for rooms whose manifest is public"
                actions={
                  <Button size="sm" variant="ghost" onClick={() => setShowSolution((s) => !s)} icon={showSolution ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}>
                    {showSolution ? "Hide" : "Reveal"}
                  </Button>
                }
              />
              <div className="px-5 py-4 text-sm">
                <p className="text-ink-2">
                  {solution.optimality_label}: <span className="font-semibold text-ink tabular">{solution.min_length}</span> actions.
                  {solution.path_efficiency != null && <> Path efficiency of this run: <span className="font-semibold text-ink tabular">{Math.floor(solution.path_efficiency * 100)}%</span>.</>}
                </p>
                {showSolution && (
                  <ol className="mt-3 space-y-1 font-mono text-[12.5px] text-ink-2">
                    {solution.solution.map((a, i) => (
                      <li key={i}><span className="text-faint tabular">{String(i + 1).padStart(2, "0")}</span> {actionText(a)}</li>
                    ))}
                  </ol>
                )}
              </div>
            </Card>
          )}
          <p className="px-1 text-xs leading-relaxed text-muted">
            Watch shows actions, observations and results only. Any agent-provided summary is labelled as such and is not a record of reasoning.
          </p>
        </aside>
      </div>
    </main>
  );
}
