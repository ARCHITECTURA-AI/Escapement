"use client";

import { FlaskConical } from "lucide-react";
import { type Check, Checks } from "./checks";
import Link from "next/link";
import { useState } from "react";
import { Button, Card, CardHeader, Hash, Notice, Page, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type Generated = { room_id: string; tier: string; instance_hash: string; min_length: number; optimality: string; attempts: number; validation: { passed: boolean; checks: Check[]; states_explored: number; max_observation_tokens: number } };

export default function LabGenerate() {
  const [tier, setTier] = useState("standard");
  const [seed, setSeed] = useState("");
  const [count, setCount] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [out, setOut] = useState<Generated[]>([]);
  const list = useApi<{ instances: { id: string; tier: string; kind: string; min_length: number; optimality: string; instance_hash: string }[] }>("/api/v1/admin/instances?kind=research");
  return (
    <Page>
      <PageHeader eyebrow={<span className="inline-flex items-center gap-2"><FlaskConical className="size-4" aria-hidden /> Local research mode</span>} title="Generate rooms" lede="Seeded generation through the real engine: solver search, replay, the full validation suite and a hashed manifest. Research rooms are playable locally and never ranked." />
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card className="h-fit p-5">
          <form
            className="space-y-4"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setErr(null);
              try {
                const r = await api<{ instances: Generated[] }>("/api/v1/admin/generate", { body: { tier, seed: seed || undefined, count } });
                setOut(r.instances);
                list.mutate();
              } catch (e2) {
                setErr(e2 instanceof Error ? e2.message : String(e2));
              } finally {
                setBusy(false);
              }
            }}
          >
            <label className="block text-sm"><span className="text-muted">Tier</span>
              <select value={tier} onChange={(e) => setTier(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-ink">
                <option value="practice">Practice</option><option value="standard">Standard</option><option value="hard">Hard</option>
              </select>
            </label>
            <label className="block text-sm"><span className="text-muted">Seed (optional)</span>
              <input value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="random if empty" className="mt-1 h-10 w-full rounded-lg border border-line-strong bg-surface px-3 font-mono text-ink" />
            </label>
            <label className="block text-sm"><span className="text-muted">Count</span>
              <input type="number" min={1} max={20} value={count} onChange={(e) => setCount(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-ink" />
            </label>
            <Button type="submit" variant="primary" loading={busy} className="w-full">Generate and validate</Button>
            {err && <Notice tone="bad">{err}</Notice>}
          </form>
        </Card>
        <div className="space-y-5">
          {out.map((g) => (
            <Card key={g.room_id}>
              <CardHeader title={g.room_id} subtitle={`${g.tier} · shortest ${g.min_length} actions (${g.optimality}) · ${g.validation.states_explored} states explored · observation ≤ ${g.validation.max_observation_tokens} tokens`} actions={<Hash value={g.instance_hash} n={8} />} />
              <div className="px-5 py-2"><Checks checks={g.validation.checks} /></div>
            </Card>
          ))}
          <Card>
            <CardHeader title="Research rooms" subtitle="Generated on this machine" />
            <ul className="divide-y divide-line">
              {list.data?.instances.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5 text-sm">
                  <Link href={`/rooms/${i.id}`} className="font-mono text-[13px] text-ink hover:underline">{i.id}</Link>
                  <span className="text-muted">{i.tier} · {i.min_length} actions · {i.optimality}</span>
                </li>
              ))}
              {list.data?.instances.length === 0 && <li className="px-5 py-4 text-sm text-muted">None yet.</li>}
            </ul>
          </Card>
        </div>
      </div>
    </Page>
  );
}
