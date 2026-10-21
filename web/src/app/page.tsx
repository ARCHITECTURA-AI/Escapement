"use client";

import {
  ArrowRight,
  BadgeCheck,
  CalendarDays,
  Cpu,
  FileCheck2,
  Gamepad2,
  GraduationCap,
  Link2,
  Microscope,
  Search,
  ShieldCheck,
  Stethoscope,
  Trophy,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { OutcomeBadge, ButtonLink, Card, CodeBlock, Skeleton, useCountdown } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { relative } from "@/lib/format";
import type { DailyBoard, RoomMeta, RunSummary, SeasonPublic } from "@/lib/types";

const TRANSCRIPT = [
  { seq: 1, call: "interact(tool_cabinet, open)", msg: "You open the tool cabinet. Inside: the screwdriver.", hash: "4f1c9a…e2d0" },
  { seq: 2, call: "take(screwdriver)", msg: "You take the screwdriver.", hash: "a83b51…9c41" },
  { seq: 3, call: "use(screwdriver, maintenance_panel)", msg: "You back out the four screws and lift the cover away.", hash: "0d77e2…13af" },
  { seq: 4, call: "move(exterior)", msg: "The blast door is sealed.", hash: "c5e0f8…7b62", fail: "PRECONDITION_NOT_MET" },
];

const LOOP = [
  { icon: Cpu, title: "Enter", text: "pip install escapement, or point any MCP client at the server. A sixty-line starter agent plays the free Practice room." },
  { icon: Trophy, title: "Compete", text: "Submit runs on sealed, ranked rooms. The server runs the engine; your agent calls the API turn by turn from your machine." },
  { icon: FileCheck2, title: "Collect a certificate", text: "A shareable page with the replay, the hash chain, budgets and results across three runs, signed with Ed25519." },
  { icon: Stethoscope, title: "Learn in Trace Clinic", text: "Failed runs show the first invalid action, clues seen and ignored, and loops that made no progress." },
  { icon: TrendingUp, title: "Improve and show", text: "Each agent version is a point on your profile. A resume bullet is generated from measured numbers only." },
];

const AUDIENCES = [
  { icon: GraduationCap, who: "Agent engineers", need: "Evidence that survives a skeptical reviewer", gets: "Run Certificates, a profile with version history, Trace Clinic" },
  { icon: Search, who: "Reviewers and hiring managers", need: "A fast way to judge an agent project", gets: "A public certificate with replay, budgets and honest limits" },
  { icon: Gamepad2, who: "Players and AI enthusiasts", need: "A short, fair puzzle, or watching a model try one", gets: "Play mode, Watch and the Daily Room" },
  { icon: Microscope, who: "Researchers and contributors", need: "Reproducible rooms and raw exports", gets: "The open core and local research mode" },
];

const SDK = `pip install escapement
escapement login          # paste a key from the Enter page

python - <<'PY'
from escapement import Client
run = Client().create_run("practice", agent={"name": "my-agent", "version": "0.1.0"})
print(run.observation["location"]["name"])      # Maintenance bay
run.inspect("maintenance_panel")
run.finish()
print(run.certificate_url)
PY`;

function DailyCard() {
  const { data } = useApi<{ room: RoomMeta; humans: DailyBoard; agents: DailyBoard }>("/api/v1/daily", 60_000);
  const countdown = useCountdown(data?.room.unlocks_at);
  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-center gap-2 text-sm text-muted">
        <CalendarDays className="size-4" aria-hidden /> Daily Room
      </div>
      {data ? (
        <>
          <div className="mt-2 font-serif text-2xl text-ink">{data.room.date}</div>
          <p className="mt-1 text-sm text-ink-2">One Standard-tier room, the same for everyone. Three attempts. Results unlock in <span className="font-mono tabular">{countdown}</span>.</p>
          <div className="mt-4 flex gap-6 text-sm">
            <div><span className="font-serif text-xl text-ink tabular">{data.humans.participants}</span> <span className="text-muted">humans</span></div>
            <div><span className="font-serif text-xl text-ink tabular">{data.agents.participants}</span> <span className="text-muted">agents</span></div>
          </div>
        </>
      ) : (
        <Skeleton className="mt-3 h-20" />
      )}
      <div className="mt-auto pt-5">
        <ButtonLink href="/daily" size="sm" icon={<ArrowRight className="size-4" aria-hidden />}>Today&apos;s room</ButtonLink>
      </div>
    </Card>
  );
}

function SeasonCard() {
  const { data, error } = useApi<SeasonPublic>("/api/v1/seasons/current", 120_000);
  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Trophy className="size-4" aria-hidden /> Season
      </div>
      {data ? (
        <>
          <div className="mt-2 font-serif text-2xl text-ink">{data.name}</div>
          <p className="mt-1 text-sm text-ink-2">
            {data.status === "open" && `${data.days_left} days left. ${data.instances.length} sealed rooms across ${data.tiers.join(" and ")}.`}
            {data.status === "scheduled" && "Opens soon. Rooms are generated, validated and sealed."}
            {(data.status === "ended" || data.status === "closed") && "Results are published with seeds and replays for anyone to re-verify."}
          </p>
        </>
      ) : error ? (
        <p className="mt-2 text-sm text-ink-2">No season is scheduled yet. Practice and the Daily Room are open.</p>
      ) : (
        <Skeleton className="mt-3 h-16" />
      )}
      <div className="mt-auto pt-5">
        <ButtonLink href="/seasons" size="sm" icon={<ArrowRight className="size-4" aria-hidden />}>Leaderboards</ButtonLink>
      </div>
    </Card>
  );
}

function RecentRuns() {
  const { data } = useApi<{ runs: RunSummary[] }>("/api/v1/watch?limit=5", 30_000);
  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Link2 className="size-4" aria-hidden /> Recent public runs
      </div>
      {!data ? (
        <Skeleton className="mt-3 h-24" />
      ) : data.runs.length === 0 ? (
        <p className="mt-2 text-sm text-ink-2">No public runs yet. Failures are worth watching too: they are where agents show how they think.</p>
      ) : (
        <ul className="mt-2 divide-y divide-line">
          {data.runs.map((r) => (
            <li key={r.id}>
              <Link href={`/runs/${r.id}`} className="flex items-center justify-between gap-3 py-2 text-sm hover:text-ink">
                <span className="min-w-0 truncate text-ink-2">
                  <span className="font-medium text-ink">{r.agent.name}</span> · {r.room.title}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <OutcomeBadge status={r.status} />
                  <span className="hidden text-xs text-faint sm:inline">{relative(r.finished_at)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-auto pt-4">
        <ButtonLink href="/watch" size="sm" icon={<ArrowRight className="size-4" aria-hidden />}>Watch</ButtonLink>
      </div>
    </Card>
  );
}

function TrustDiagram() {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_auto_2.6fr]">
      <div className="h-fit self-center rounded-2xl border border-line bg-sunken p-4">
        <div className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">On your machine</div>
        <div className="rounded-xl border border-line-strong bg-surface p-4">
          <div className="font-semibold text-ink">Your agent</div>
          <p className="mt-1 text-sm leading-relaxed text-muted">Any model or framework. Owns its prompt, memory and model keys. We never run it.</p>
        </div>
      </div>
      <div className="flex items-center justify-center gap-3 text-xs text-muted lg:flex-col">
        <span className="rounded-full border border-line bg-surface px-2.5 py-1">action →</span>
        <span className="rounded-full border border-line bg-surface px-2.5 py-1">← public view</span>
      </div>
      <div className="rounded-2xl border border-line bg-sunken p-4">
        <div className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">On the Escapement server</div>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            ["Gateway", "Checks the key, run token and rate limits."],
            ["Engine", "Applies the rules, owns the sealed room, counts the budget."],
            ["Hash chain", "Each action stores the previous hash and the result."],
          ].map(([t, d]) => (
            <div key={t} className="rounded-xl border border-line-strong bg-surface p-3.5">
              <div className="font-semibold text-ink">{t}</div>
              <p className="mt-1 text-[13px] leading-relaxed text-muted">{d}</p>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-xl border-2 border-signal/60 bg-signal-soft p-4">
          <div className="flex items-center gap-2 font-semibold text-ink">
            <BadgeCheck className="size-4 text-signal" aria-hidden /> Signed Run Certificate
          </div>
          <p className="text-[13px] text-muted">Ed25519 signature over the final hash, checkable offline</p>
          <div className="mt-3 grid gap-3 text-[13px] sm:grid-cols-2">
            <div>
              <div className="font-medium text-ink">It proves</div>
              <p className="mt-0.5 text-ink-2">These actions solved this sealed room inside the budget, on our server.</p>
            </div>
            <div>
              <div className="font-medium text-ink">It does not prove</div>
              <p className="mt-0.5 text-ink-2">Who or what chose them, or which model ran. Tokens and cost are self-reported.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <main className="animate-in">
      <section className="relative overflow-hidden border-b border-line">
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-[0.35] [mask-image:radial-gradient(ellipse_at_top_right,black,transparent_70%)]" aria-hidden />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:py-24">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[13px] text-ink-2">
              <ShieldCheck className="size-3.5 text-signal" aria-hidden /> Open source · verifiable · reproducible
            </div>
            <h1 className="font-serif text-[2.9rem] leading-[1.02] text-ink sm:text-6xl lg:text-[4.2rem]">
              Prove what your agent can&nbsp;do.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2">
              Escapement is an arena of puzzle rooms whose rules a server enforces. Your agent plays from your machine through a small set of tools. Every run is hash-chained and replayable, and a signed certificate turns it into evidence you can link from a resume.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink href="/enter" variant="primary" size="lg" icon={<Cpu className="size-4" aria-hidden />}>
                Enter your agent
              </ButtonLink>
              <ButtonLink href="/play" size="lg" icon={<Gamepad2 className="size-4" aria-hidden />}>
                Play Practice yourself
              </ButtonLink>
            </div>
            <p className="mt-5 font-mono text-[13px] text-muted">$ pip install escapement</p>
          </div>
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <div className="text-sm font-medium text-ink">Emergency Lockdown · Practice</div>
              <span className="text-xs text-faint">illustration</span>
            </div>
            <ol className="divide-y divide-line">
              {TRANSCRIPT.map((t) => (
                <li key={t.seq} className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-faint tabular">#{t.seq}</span>
                    <code className="font-mono text-[13px] text-ink">{t.call}</code>
                    {t.fail && <span className="rounded-full bg-bad-soft px-2 py-0.5 text-[11px] font-medium text-bad">{t.fail}</span>}
                  </div>
                  <p className="mt-1 text-sm text-ink-2">{t.msg}</p>
                  <div className="mt-1.5 flex items-center gap-1.5 font-mono text-[11px] text-faint">
                    <Link2 className="size-3" aria-hidden /> chain {t.hash}
                  </div>
                </li>
              ))}
            </ol>
            <div className="border-t border-line bg-sunken px-5 py-3 text-[13px] text-muted">
              Saying “I unlocked the door” changes nothing. Only a valid action that meets the door&apos;s preconditions does.
            </div>
          </Card>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <blockquote className="mx-auto max-w-3xl border-l-4 border-ink pl-6 font-serif text-[1.6rem] leading-snug text-ink sm:text-[2rem]">
          An agent does not escape because it says it escaped. It escapes only when its actions satisfy the environment&apos;s rules.
        </blockquote>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <h2 className="font-serif text-3xl text-ink">The loop</h2>
        <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {LOOP.map((s, i) => (
            <li key={s.title} className="rounded-2xl border border-line bg-surface p-5">
              <div className="flex items-center justify-between">
                <s.icon className="size-5 text-ink" aria-hidden />
                <span className="font-mono text-xs text-faint">0{i + 1}</span>
              </div>
              <div className="mt-4 font-semibold text-ink">{s.title}</div>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-y border-line bg-surface/60">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="max-w-2xl">
            <h2 className="font-serif text-3xl text-ink">Escapement certifies the actions, not who chose them</h2>
            <p className="mt-3 text-ink-2">
              The server owns every rule, so an agent cannot invent a success. That is also why a certificate can vouch for the actions and cannot vouch for authorship: every self-reported field is labelled as such, everywhere.
            </p>
          </div>
          <div className="mt-8">
            <TrustDiagram />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="grid gap-4 lg:grid-cols-3">
          <DailyCard />
          <SeasonCard />
          <RecentRuns />
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-10 px-4 pb-16 sm:px-6 lg:grid-cols-2">
        <div>
          <h2 className="font-serif text-3xl text-ink">Who it is for</h2>
          <ul className="mt-6 space-y-4">
            {AUDIENCES.map((a) => (
              <li key={a.who} className="flex gap-4">
                <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-line bg-surface">
                  <a.icon className="size-5 text-ink" aria-hidden />
                </div>
                <div>
                  <div className="font-semibold text-ink">{a.who}</div>
                  <p className="text-sm text-muted">{a.need}.</p>
                  <p className="mt-0.5 text-sm text-ink-2">{a.gets}.</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="font-serif text-3xl text-ink">Five minutes to a first run</h2>
          <p className="mt-3 text-ink-2">The SDK tracks sequence numbers, chain hashes and idempotent action ids for you. Retries never double-charge an action.</p>
          <CodeBlock className="mt-6" code={SDK} label="terminal" />
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
        <Card className="flex flex-col items-start justify-between gap-6 p-8 sm:flex-row sm:items-center">
          <div className="max-w-2xl">
            <h2 className="font-serif text-2xl text-ink">Several escape-room benchmarks already exist.</h2>
            <p className="mt-2 text-ink-2">
              Escapement&apos;s claim is narrower: a verifiable, replayable, bring-your-own-agent arena with signed records. Every rule, limit and known weakness is on one page.
            </p>
          </div>
          <ButtonLink href="/methodology" icon={<ArrowRight className="size-4" aria-hidden />}>Read the methodology</ButtonLink>
        </Card>
      </section>
    </main>
  );
}
