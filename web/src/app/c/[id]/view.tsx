"use client";

import clsx from "clsx";
import { AlertOctagon, BadgeCheck, CheckCircle2, Download, Eye, Loader2, ShieldCheck, ShieldQuestion, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge, Button, ButtonLink, Card, CodeBlock, CopyButton, ErrorState, Hash, KV, Notice, OutcomeBadge, Page, Skeleton, Source } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, duration, usd } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { CertificatePage } from "@/lib/types";

type VerifyReport = { ok: boolean; signature_valid: boolean; level: string; key_id: string; problems: string[]; notes: string[]; revoked: boolean; checked_at: string };

const LEVELS: Record<string, { label: string; text: string }> = {
  signature: { label: "Signature", text: "Signed by a published Escapement key and unmodified." },
  chain: { label: "Hash chain", text: "The replay's hash chain recomputes to the certified final hash." },
  full: { label: "Full re-simulation", text: "The recorded actions re-run through the pinned engine against the room manifest and reproduce every hash." },
};

export function CertificateView({ id }: { id: string }) {
  const { data, error } = useApi<CertificatePage>(`/api/v1/certificates/${id}`);
  const [report, setReport] = useState<VerifyReport | null>(null);
  const [checking, setChecking] = useState(false);

  if (error) return <Page><ErrorState error={error} /></Page>;
  if (!data) return <Page><Skeleton className="h-12 w-96" /><Skeleton className="mt-6 h-[520px]" /></Page>;

  const c = data.certificate;
  if (c.tombstone)
    return (
      <Page>
        <Notice tone="bad" icon={<AlertOctagon className="size-5" aria-hidden />} title="This certificate has been revoked">
          {c.reason ?? data.revocation_reason} Revoked {dateTime(data.revoked_at)}.
        </Notice>
      </Page>
    );

  const human = c.agent.agent_type === "human";
  const attested = c.agent.model_attested;
  const verify = async () => {
    setChecking(true);
    try {
      setReport(await api<VerifyReport>(`/api/v1/certificates/${id}/verify`));
    } finally {
      setChecking(false);
    }
  };

  return (
    <Page>
      {data.revoked && (
        <Notice tone="bad" icon={<AlertOctagon className="size-5" aria-hidden />} title="Revoked" className="mb-6">
          An Escapement administrator revoked this certificate on {dateTime(data.revoked_at)}: {data.revocation_reason}
        </Notice>
      )}
      <Card className="overflow-hidden">
        <div className="relative border-b border-line bg-sunken/70 px-6 py-8 sm:px-10">
          <div className="pointer-events-none absolute right-6 top-6 hidden size-24 rotate-[-8deg] place-items-center rounded-full border-2 border-signal/40 text-center sm:grid" aria-hidden>
            <div>
              <ShieldCheck className="mx-auto size-6 text-signal" />
              <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-signal-ink">Ed25519</div>
            </div>
          </div>
          <div className="text-[13px] font-medium uppercase tracking-[0.16em] text-muted">Escapement · Run Certificate</div>
          <h1 className="mt-3 max-w-3xl font-serif text-[2.2rem] leading-[1.1] text-ink sm:text-5xl">
            {human ? "A human player" : <>{c.agent.name} <span className="text-muted">{c.agent.version}</span></>}{" "}
            {c.outcome === "escaped" ? "escaped" : "did not escape"} {c.room.title}.
          </h1>
          <div className="mt-5 flex flex-wrap items-center gap-2">
            <OutcomeBadge status={c.outcome} size="lg" />
            <Badge>{c.room.tier} tier</Badge>
            <Badge>{c.mode}</Badge>
            {c.room.season && <Badge>season {c.room.season}</Badge>}
            {c.assisted && <Badge tone="warn">Assisted with hints</Badge>}
          </div>
          <div className="mt-8 grid grid-cols-2 gap-6 sm:grid-cols-4">
            <Fact label="Actions used" value={`${c.actions_used} / ${c.action_budget}`} />
            <Fact label="Run set on this room" value={`${c.run_set.escapes} of ${c.run_set.runs} escaped`} />
            <Fact label="Malformed requests" value={String(c.malformed_count)} />
            <Fact label="Server wall time" value={duration(c.wall_time_ms)} />
          </div>
        </div>

        <div className="grid gap-0 lg:grid-cols-2">
          <section className="border-b border-line px-6 py-6 sm:px-10 lg:border-b-0 lg:border-r">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink"><Source kind="server" /> Measured by the server</h2>
            <dl className="mt-3">
              <KV k="Certificate" v={<span className="font-mono text-[13px]">{c.certificate_id}</span>} />
              <KV k="Issued" v={dateTime(c.issued_at)} />
              <KV k="Room" v={`${c.room.room_id} (${c.room.family.replaceAll("_", " ")})`} />
              <KV k="Room instance hash" v={<Hash value={c.room.instance_hash} />} />
              <KV k="Engine / protocol" v={<span className="font-mono text-[13px]">{c.engine_version} / v{c.protocol_version}</span>} />
              <KV k="Chain length" v={String(c.chain_length)} />
              <KV k="Final chain hash" v={<Hash value={c.final_chain_hash} />} />
              <KV k="Signing key" v={<span className="font-mono text-[13px]">{c.key_id}</span>} />
            </dl>
          </section>
          <section className="px-6 py-6 sm:px-10">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">{attested ? <Source kind="attested" /> : <Source kind="self" />} {attested ? "First-party reference agent" : "Declared by the client"}</h2>
            <dl className="mt-3">
              <KV k="Agent" v={human ? "Human player (browser)" : `${c.agent.name} ${c.agent.version ?? ""}`} />
              {!human && <KV k="Model" v={c.agent.model ?? "—"} source={attested ? "attested" : "self"} />}
              {attested && <KV k="Provider" v={c.agent.provider ?? "—"} source="attested" />}
              {!human && <KV k="Framework" v={c.agent.framework ?? "—"} source={attested ? undefined : "self"} />}
              {!human && <KV k="Memory strategy" v={c.agent.memory ?? "—"} source={attested ? undefined : "self"} />}
              {!human && <KV k="Tokens" v={c.usage.tokens_in != null ? `${c.usage.tokens_in} in · ${c.usage.tokens_out ?? 0} out` : "not reported"} source={attested ? "attested" : "self"} />}
              {!human && <KV k="Cost" v={usd(c.usage.cost_usd_micros)} source="self" />}
              {!human && <KV k="Model decisions" v={c.usage.model_decisions != null ? String(c.usage.model_decisions) : "not reported"} source={attested ? "attested" : "self"} />}
            </dl>
          </section>
        </div>

        <div className="grid gap-6 border-t border-line bg-sunken/40 px-6 py-6 sm:px-10 md:grid-cols-2">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-ink"><CheckCircle2 className="size-4 text-good" aria-hidden /> It proves</div>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{c.proves}</p>
          </div>
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-ink"><ShieldQuestion className="size-4 text-self" aria-hidden /> It does not prove</div>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{c.does_not_prove}</p>
          </div>
        </div>
      </Card>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[1.2fr_1fr]">
        <Card className="p-6">
          <h2 className="font-semibold text-ink">Verification</h2>
          <p className="mt-1 text-sm text-ink-2">{data.verification.explanation}</p>
          <ol className="mt-4 space-y-2">
            {(["signature", "chain", "full"] as const).map((lvl) => {
              const avail = ["signature", "chain", "full"].indexOf(lvl) <= ["signature", "chain", "full"].indexOf(data.verification.available);
              const passed = report && ["signature", "chain", "full"].indexOf(lvl) <= ["signature", "chain", "full"].indexOf(report.level) && report.signature_valid;
              return (
                <li key={lvl} className={clsx("flex items-start gap-3 rounded-xl border px-4 py-3", avail ? "border-line bg-surface" : "border-dashed border-line bg-transparent opacity-70")}>
                  <span className="mt-0.5">
                    {report ? (passed ? <CheckCircle2 className="size-4 text-good" aria-label="Passed" /> : <XCircle className="size-4 text-faint" aria-label="Not checked" />) : <ShieldCheck className="size-4 text-faint" aria-hidden />}
                  </span>
                  <span>
                    <span className="text-sm font-medium text-ink">{LEVELS[lvl].label}</span>
                    {!avail && <span className="ml-2 text-xs text-muted">available once the room manifest is published</span>}
                    <span className="block text-[13px] text-muted">{LEVELS[lvl].text}</span>
                  </span>
                </li>
              );
            })}
          </ol>
          {report && (
            <div className="mt-4">
              {report.ok ? (
                <Notice tone="good" icon={<BadgeCheck className="size-4" aria-hidden />} title={`Verified at the ${LEVELS[report.level]?.label.toLowerCase() ?? report.level} level`}>
                  Checked {dateTime(report.checked_at)} by the server. You can repeat this offline.
                </Notice>
              ) : (
                <Notice tone="bad" icon={<XCircle className="size-4" aria-hidden />} title="Verification failed">
                  <ul className="list-disc pl-4">{report.problems.map((p) => <li key={p}>{p}</li>)}</ul>
                </Notice>
              )}
            </div>
          )}
          <div className="mt-5 flex flex-wrap gap-2">
            <Button variant="primary" onClick={verify} loading={checking} icon={checking ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <ShieldCheck className="size-4" aria-hidden />}>
              Verify now
            </Button>
            {data.run && !data.run.embargo_until && <ButtonLink href={`/runs/${data.run.id}`} icon={<Eye className="size-4" aria-hidden />}>Watch the replay</ButtonLink>}
            <ButtonLink href={`/api/v1/certificates/${id}/download`} external icon={<Download className="size-4" aria-hidden />}>certificate.json</ButtonLink>
          </div>
          {data.run?.embargo_until && <p className="mt-3 text-sm text-muted">The replay is embargoed until {dateTime(data.run.embargo_until)}.</p>}
        </Card>
        <Card className="p-6">
          <h2 className="font-semibold text-ink">Check it yourself, offline</h2>
          <p className="mt-1 text-sm text-ink-2">The verifier is open source. It checks the Ed25519 signature against the published key set, recomputes the hash chain from the replay and, with the manifest, re-simulates every action.</p>
          <CodeBlock
            className="mt-4"
            code={`pip install escapement
escapement export ${c.run_id}
escapement verify ${c.run_id}.certificate.json \\
  --replay ${c.run_id}.replay.json${data.verification.manifest_public ? ` \\\n  --manifest ${c.room.room_id}.manifest.json` : ""}`}
          />
          <div className="mt-3 flex items-center gap-2 text-xs text-muted">
            Signature <code className="truncate font-mono">{c.signature.slice(0, 32)}…</code>
            <CopyButton value={c.signature} />
          </div>
        </Card>
      </div>
    </Page>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[13px] text-muted">{label}</div>
      <div className="mt-0.5 font-serif text-2xl text-ink tabular">{value}</div>
    </div>
  );
}
