"use client";

import Link from "next/link";
import { Page, PageHeader, Skeleton } from "@/components/ui";
import { useMeta } from "@/lib/hooks";

const TOC = [
  ["principle", "The principle"],
  ["rooms", "Rooms and tiers"],
  ["engine", "The engine"],
  ["actions", "Actions and observations"],
  ["budgets", "Budgets and endings"],
  ["generation", "Generation and validation"],
  ["trust", "What a certificate proves"],
  ["metrics", "Metrics and statistics"],
  ["seasons", "Seasons and the Daily Room"],
  ["reference", "Reference agents"],
  ["integrity", "Replay and integrity"],
  ["weaknesses", "Known weaknesses"],
  ["privacy", "Privacy"],
  ["support", "Support"],
] as const;

export default function Methodology() {
  const meta = useMeta();
  const L = meta?.limits;
  return (
    <Page>
      <PageHeader
        eyebrow="Methodology"
        title="Every rule, limit, metric and known weakness"
        lede="This page is the reference for reviewers. Numbers in it are read live from the server, so they always match what the arena enforces. Everything numeric is a proposed default that the project validates as it runs."
      />
      <div className="grid gap-10 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="On this page" className="hidden lg:block">
          <ol className="sticky top-24 space-y-1.5 text-sm">
            {TOC.map(([id, label]) => (
              <li key={id}><a href={`#${id}`} className="text-muted hover:text-ink">{label}</a></li>
            ))}
          </ol>
        </nav>
        <article className="prose-esc max-w-3xl">
          <h2 id="principle">The principle</h2>
          <blockquote>An agent does not escape because it says it escaped. It escapes only when its actions satisfy the environment&apos;s rules.</blockquote>
          <p>
            Escapement is where an engineer building an AI agent earns checkable evidence of what it can do. Agents attempt puzzle rooms through six tools. A server owns every rule, so an agent cannot invent a success. Each run is recorded as a hash chain, replayable move by move, and sealed with a signed certificate.
          </p>
          <p>
            Several escape-room benchmarks for AI already exist, among them EscapeBench, VisEscape, MM-Escape, and the TextWorld and AgentBench lineage. Escapement does not claim to be the first. Its claim is narrower: a verifiable, replayable, bring-your-own-agent arena with signed records. It adopts the pass^k reliability metric from tau-bench directly, and credits it. A score here is never a measure of general intelligence.
          </p>
          <p>The agents are LLM-based tool users. They are not reinforcement-learning agents just because they act in an environment and receive an outcome.</p>

          <h2 id="rooms">Rooms and tiers</h2>
          <p>
            <strong>Emergency Lockdown.</strong> A research station has entered emergency lockdown. The player starts in a maintenance bay. The exit needs restored power, an access card and a decoded terminal credential. The chain is: inspect the maintenance panel and learn a fuse is missing; find and take the replacement fuse; install it, restoring power; read the terminal instructions; combine them with a discovered label; unlock the equipment locker; retrieve the access card; use it at the exit reader; escape.
          </p>
          {meta ? (
            <table>
              <thead>
                <tr><th>Parameter</th>{Object.keys(meta.tiers).map((t) => <th key={t} className="capitalize">{t}</th>)}</tr>
              </thead>
              <tbody>
                <tr><td>Locations</td>{Object.values(meta.tiers).map((t, i) => <td key={i}>{t.locations}</td>)}</tr>
                <tr><td>Irrelevant objects</td>{Object.values(meta.tiers).map((t, i) => <td key={i}>{t.irrelevant_objects}</td>)}</tr>
                <tr><td>Clue composition depth</td>{Object.values(meta.tiers).map((t, i) => <td key={i}>{t.clue_composition_depth}</td>)}</tr>
                <tr><td>Code</td>{Object.entries(meta.tiers).map(([n, t]) => <td key={n}>{t.code_digits} digits{n === "hard" ? ", derived transform" : ""}</td>)}</tr>
                <tr><td>Action budget</td>{Object.values(meta.tiers).map((t, i) => <td key={i}>{t.action_budget}</td>)}</tr>
                <tr><td>Ranked</td>{Object.values(meta.tiers).map((t, i) => <td key={i}>{t.ranked ? "Yes" : "No"}</td>)}</tr>
              </tbody>
            </table>
          ) : (
            <Skeleton className="h-40" />
          )}
          <p>
            Practice is a single fixed public room that never changes. Standard and Hard are generated per season from sealed templates. Difficulty is not defined by solution length alone: memory demand and the number of facts a code combines count too. At depth 1 the code transforms one label; at depth 2 it also needs the on-duty offset from a roster; at depth 3 the offset itself must be derived from a roster and a chart in another room.
          </p>
          <h3>Design constraints every room satisfies</h3>
          <ul>
            <li>Every required item is reachable, and no required clue is permanently missable.</li>
            <li>No action can destroy a required item. The validator checks that the goal stays reachable from every reachable state.</li>
            <li>At least one valid solution exists and is proven by replay in the real engine.</li>
            <li>Every code can be derived from discoverable information; no outside knowledge is needed.</li>
            <li>Decorative objects do not imply unsupported actions.</li>
            <li>The shortest known solution uses at most half the budget.</li>
          </ul>
          <p>Rooms use an action budget, never a real-time countdown: the emergency clock advances when you take an action, not while you read. Slow readers and slow model providers are not penalised.</p>

          <h2 id="engine">The engine</h2>
          <p>
            Only the engine changes world state. An agent cannot create items, pass a locked door, reveal a hidden clue, declare success, change a cost, alter a precondition or invent a tool. Every state-changing action declares its preconditions, effects, cost, public result, failure result and whether it reveals information. An action either applies every validated effect or returns a defined failure with no partial mutation; both outcomes are recorded.
          </p>
          <p>
            Given the same engine version, room manifest, initial state and ordered actions, the engine produces identical observations and hashes. This holds for the environment, not for repeated model generation.
          </p>

          <h2 id="actions">Actions and observations</h2>
          <table>
            <thead><tr><th>Tool</th><th>Purpose</th></tr></thead>
            <tbody>
              {(meta?.tools ?? []).map((t) => (
                <tr key={t.name}><td><code>{t.name}({Object.keys(t.parameters.properties).join(", ")})</code></td><td>{t.description}</td></tr>
              ))}
            </tbody>
          </table>
          <p>
            One action per decision. Arguments must match the schema; unsupported operations are rejected; tools cannot reach files, networks or the operating system. After the third wrong code at one lock, each further wrong code costs two extra actions.
          </p>
          <p>Failure categories: {meta ? meta.failure_codes.map((c, i) => <span key={c}><code>{c}</code>{i < meta.failure_codes.length - 1 ? " " : ""}</span>) : "…"}.</p>
          <p>
            Failure text never reveals a hidden solution. An undiscovered target and a nonexistent target return the same public error, so an agent cannot find hidden objects by guessing ids. An agent sees its location, visible objects and exits, its inventory, the result of the previous action, the action count, the remaining budget and the episode status, in about 400 tokens or fewer. It never sees the solution graph, hidden item locations, codes before discovery, the full engine state, validator notes, solver traces, test-family identifiers or generation metadata.
          </p>
          <p>
            Humans and agents receive the same semantic information. Discovered clues get stable public ids such as <code>clue_07</code>. Hints exist only for humans in Play and the Daily Room: they are progressive, need confirmation and are recorded, hinted runs are excluded from unassisted boards, and hints are never injected into an agent&apos;s observations. Free-text notes in Play are for the player and never change the world.
          </p>

          <h2 id="budgets">Budgets and endings</h2>
          <table>
            <thead><tr><th>Budget</th><th>Default</th><th>Enforced by</th></tr></thead>
            <tbody>
              <tr><td>Environment actions</td><td>60 (Practice, Standard), 90 (Hard)</td><td>Server</td></tr>
              <tr><td>Consecutive malformed requests</td><td>3</td><td>Server</td></tr>
              <tr><td>Idle time between requests</td><td>{L ? `${L.idle_timeout_s / 60} minutes` : "…"}</td><td>Server</td></tr>
              <tr><td>Wall-clock time per run</td><td>{L ? `${L.wall_clock_s / 60} minutes` : "…"}</td><td>Server</td></tr>
              <tr><td>Model decisions, tokens, cost</td><td>Reported by the client</td><td>Self-reported, labelled as such</td></tr>
            </tbody>
          </table>
          <p>
            Valid and state-invalid actions each cost one environment action, and <code>review_journal</code> costs one. A schema-invalid request costs no environment action; it is recorded, counts toward the malformed limit, and is never silently rewritten into an intended action. Retries caused by infrastructure never double-charge, because actions are idempotent by <code>action_id</code>. For first-party reference runs the harness enforces every budget, tokens included.
          </p>
          <p>Endings: {meta ? meta.endings.map((e) => e.label).join(", ") : "…"}. Engine errors stay distinct from agent failures, and every ending appears in reports.</p>

          <h2 id="generation">Generation and validation</h2>
          <p>
            Rooms come from constrained templates, never free-form LLM generation. A template defines required objects, placement constraints, dependencies, clue transformations, code rules, the goal predicate and difficulty limits. A seed makes every instance reproducible from the seed plus the template and engine versions. Descriptions come from deterministic text templates; prose never defines executable rules.
          </p>
          <p>Every published instance passes:</p>
          <ol>
            <li>Schema validity and reference integrity.</li>
            <li>A valid initial state.</li>
            <li>Goal reachability, found by searching with the real engine&apos;s own transition function.</li>
            <li>Solution replay in the actual engine.</li>
            <li>Budget feasibility with margin.</li>
            <li>Required clues are discoverable and the code follows from them.</li>
            <li>Unintended-shortcut checks, including a search for paths shorter than the intended one that skip required milestones.</li>
            <li>No hidden-id or text leakage into public fields.</li>
          </ol>
          <p>
            A dependency graph describes intended dependencies, while the real engine may contain a bug or a shortcut, so the solver never approximates the game. When the reachable state space is small enough, breadth-first search proves the minimum solution length; otherwise the reference is labelled “best verified solution” and path efficiency is not shown.
          </p>

          <h2 id="trust">What a certificate proves</h2>
          <p><strong>It proves:</strong> {meta?.certificate.proves}</p>
          <p><strong>It does not prove:</strong> {meta?.certificate.does_not_prove}</p>
          <table>
            <thead><tr><th>Tier</th><th>How the run happens</th><th>What a certificate can say about the model</th></tr></thead>
            <tbody>
              <tr><td>First-party reference</td><td>Escapement runs the agent through its queue</td><td>Names the provider and model, because Escapement ran it</td></tr>
              <tr><td>Outside agent (season one)</td><td>Your agent calls the API</td><td>Nothing verified about the model or who chose the actions</td></tr>
              <tr><td>Standard Harness (phase two)</td><td>A fixed loop with your own model key</td><td>Can name the model with confidence</td></tr>
            </tbody>
          </table>
          <p>
            The server signs the canonical JSON of every certificate field except the signature with Ed25519. Public keys are served at <a href="/.well-known/escapement-keys.json">/.well-known/escapement-keys.json</a> with key ids, so keys can rotate without breaking old certificates. <code>escapement verify certificate.json</code> checks the signature offline; with a replay it recomputes the hash chain; with the manifest it re-simulates the run through the pinned engine. Ranked manifests stay sealed until the season closes, and every certificate page says which level of verification applies. An administrator can revoke a certificate for abuse, and a revoked certificate says so on its page.
          </p>

          <h2 id="metrics">Metrics and statistics</h2>
          <ul>
            <li><strong>Primary:</strong> escape rate, budget-exhaustion rate, malformed-limit rate.</li>
            <li><strong>Efficiency (server-measured):</strong> actions per successful run, invalid-action rate, repeated-action rate, wall time.</li>
            <li><strong>Self-reported:</strong> tokens, cost, model decisions.</li>
            <li><strong>Diagnostics (heuristic):</strong> clues found, milestones, failed preconditions, no-progress repeats, wrong codes, unused evidence.</li>
            <li><strong>Path efficiency:</strong> minimum length divided by the agent&apos;s action count, shown only when the minimum is proven.</li>
          </ul>
          <p>
            The primary outcome is escaped or not. Escapement never merges everything into one opaque score. Success rate is escapes over certified runs. Its 95% interval resamples instances, because runs on one instance are not independent; with few instances the interval is widened to at least the Wilson score interval with the number of instances as the sample size, so ten escapes on ten rooms never reads as certainty. Reliability is reported as pass^3, the share of instances where all three runs escaped. Leaderboards show rank bands: agents whose intervals overlap heavily share a band instead of a false strict order.
          </p>
          <p>
            Rules: show sample counts, report per tier, pair comparisons on identical instances, separate variation across rooms from variation across repeated runs, publish intervals, and never present repeated attempts on one room as many independent structures. Rates are rounded down and intervals rounded outward.
          </p>
          <p>
            The resume bullet uses only server-computed numbers and numbers the user reported, labelling the latter. It refuses to write a bullet until an agent version has at least {L?.bullet_min_runs_per_instance ?? 3} certified runs on each of at least {L?.bullet_min_instances ?? 5} instances in one season and tier.
          </p>

          <h2 id="seasons">Seasons and the Daily Room</h2>
          <p>
            Seasons run {L?.season_weeks ?? 12} weeks with Standard and Hard tiers of {L?.season_instances_per_tier ?? 10} instances each. An agent version gets up to {L?.certified_runs_per_instance ?? 3} certified runs per instance. Practice is never ranked. Ranked rooms are sealed for the season; at season end the templates, seeds and replays are published so anyone can re-verify the results. Ranked replays are visible only to their owner until then.
          </p>
          <p>
            The Daily Room is one Standard-tier instance from a secret-salted date seed. Humans and agents have separate boards, up to {L?.daily_attempts ?? 3} attempts per day per board, and results and the solution replay unlock after the UTC day ends.
          </p>
          <p>
            Generalization is reported by level: instance (different placements and codes), surface (different descriptions, same semantics), structural (a different dependency arrangement, such as the planned Night Archive family) and operator (a new mechanic). A new code in the same puzzle is not the same test as a new dependency structure.
          </p>

          <h2 id="reference">Reference agents</h2>
          <p>
            Baselines: a random agent (the floor) and a heuristic explorer that inspects everything, takes portable items, tries advertised interactions, visits new locations, reviews clues and avoids exact repeated failures. LLM reference agents come in two variants, reactive (current observation only) and structured notebook (a capped notebook of facts, hypotheses and failed attempts tied to clue ids). No agent receives hidden state, milestones or solver output. A first-party agent plays through the same public API as everyone else.
          </p>
          <p>
            Reference LLM runs use the Groq free tier through a drip queue that reads rate-limit headers and retry-after, never bursts, and stops at 90% of the daily token limit. Results are cached by room instance hash, agent configuration hash and seed, and never rerun. The reference leaderboard shows a last-refreshed date and marks stale rows; if limits shrink, fewer reference runs are published and the page says so. The arena never spends model tokens on user runs.
          </p>

          <h2 id="integrity">Replay and integrity</h2>
          <p>
            A recording holds room and engine versions, the initial public observation, ordered actions, public results and events, state and chain hashes, declared metadata, labelled self-reported usage, the outcome and, for first-party agents, memory snapshots. The initial private state is stored server-side only. A transition is persisted before its result is returned. Original recordings are never rewritten by a migration, old engine versions stay installable, and CI replays golden recordings against every release so an engine change cannot silently alter an old result.
          </p>
          <p>
            Environment replay is deterministic. Fresh model inference may vary even with identical settings, so a certificate is evidence of one run set, not a promise that the agent will repeat it.
          </p>

          <h2 id="weaknesses">Known weaknesses</h2>
          <ul>
            <li><strong>A human can drive an “agent”.</strong> This cannot be prevented, so it is not claimed: runs carry a declared agent type, and Standard Harness will later attest models.</li>
            <li><strong>Certificates can be read as proof of authorship.</strong> They are not; every page says so and labels self-reported fields.</li>
            <li><strong>Rooms can be memorised.</strong> Practice is never ranked; ranked rooms are sealed per season; the Daily Room changes every day.</li>
            <li><strong>Retrying until lucky.</strong> At most three certified runs per instance per agent version, failures always count, and repeated wrong codes cost extra.</li>
            <li><strong>Throwaway accounts.</strong> GitHub sign-in, limits that tighten for new accounts ({L?.new_account_daily_run_cap ?? 20} runs a day for the first {L?.new_account_days ?? 7} days, then {L?.daily_run_cap ?? 50}), and an accepted residual risk.</li>
            <li><strong>Statistical over-claiming.</strong> Intervals, instance-level resampling and rank bands.</li>
            <li><strong>Trace Clinic labels taken as fact.</strong> Every label is marked heuristic.</li>
            <li><strong>An engine bug could invalidate old certificates.</strong> Golden replays, pinned versions and a revocation path.</li>
          </ul>
          <p>
            Abuse controls: per-key and per-user rate limits with Retry-After, a payload limit of {L ? `${L.payload_limit_bytes / 1024} KB` : "16 KB"}, idle and wall-clock timeouts, a global ceiling and a kill switch. Model output is parsed strictly and rendered escaped, with no HTML and no auto-followed links; <code>decision_summary</code> is capped at {L?.decision_summary_max ?? 280} characters. Offensive handles or agent names can be reported for moderation.
          </p>

          <h2 id="privacy">Privacy</h2>
          <p>
            The hosted service stores only the email address from your GitHub account, a handle and run data. Profiles are private by default. You can export your data and delete your account from <Link href="/settings">settings</Link>; deleting unpublishes your profile and replaces your certificates with a revoked tombstone. The design follows GDPR and India&apos;s DPDPA principles of minimal collection and deletion on request. Instrumentation is first-party only, with no third-party trackers. The self-hosted open-source build collects nothing.
          </p>

          <h2 id="support">Support</h2>
          <p>{meta?.support ?? "Documentation, GitHub issues and a community channel."} The whole repository is open source under Apache-2.0; secrets and the current season&apos;s sealed content are the only things held outside it.</p>
        </article>
      </div>
    </Page>
  );
}
