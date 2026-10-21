"use client";

import { FlaskConical } from "lucide-react";
import { useState } from "react";
import { Button, Card, CardHeader, Notice, Page, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { actionText } from "@/lib/format";
import { Checks } from "../generate/checks";

type Report = { passed: boolean; checks: { id: string; name: string; passed: boolean; detail: string }[]; min_length: number | null; optimality: string; states_explored: number };

export default function LabValidate() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<{ report: Report; solution: { tool: string; arguments: Record<string, string> }[] } | null>(null);
  return (
    <Page>
      <PageHeader eyebrow={<span className="inline-flex items-center gap-2"><FlaskConical className="size-4" aria-hidden /> Local research mode</span>} title="Validate a manifest" lede="Paste a room manifest. The suite checks schema and references, the initial state, reachability with the real engine, replay, budget margin, clue derivability, shortcuts, dead ends and leakage." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <label htmlFor="manifest" className="text-sm text-muted">Manifest JSON</label>
          <textarea id="manifest" value={text} onChange={(e) => setText(e.target.value)} rows={22} spellCheck={false} className="mt-1 w-full rounded-lg border border-line-strong bg-paper p-3 font-mono text-[12.5px] text-ink" placeholder='{"format": "escapement-manifest/1", ...}' />
          <div className="mt-3 flex gap-2">
            <Button
              variant="primary"
              loading={busy}
              onClick={async () => {
                setBusy(true);
                setErr(null);
                try {
                  setRes(await api("/api/v1/admin/validate", { body: { manifest: JSON.parse(text) } }));
                } catch (e) {
                  setErr(e instanceof Error ? e.message : String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Validate
            </Button>
            <Button
              variant="ghost"
              onClick={async () => {
                const m = await api<Record<string, unknown>>("/api/v1/rooms/practice/manifest");
                setText(JSON.stringify(m, null, 2));
              }}
            >
              Load Practice
            </Button>
          </div>
          {err && <Notice tone="bad" className="mt-3">{err}</Notice>}
        </Card>
        {res && (
          <Card>
            <CardHeader title={res.report.passed ? "Valid" : "Invalid"} subtitle={res.report.min_length != null ? `Shortest solution ${res.report.min_length} actions (${res.report.optimality}), ${res.report.states_explored} states explored` : undefined} />
            <div className="px-5 py-2"><Checks checks={res.report.checks} /></div>
            {res.solution.length > 0 && (
              <ol className="border-t border-line px-5 py-4 font-mono text-[12.5px] text-ink-2">
                {res.solution.map((a, i) => <li key={i}><span className="text-faint">{String(i + 1).padStart(2, "0")}</span> {actionText(a)}</li>)}
              </ol>
            )}
          </Card>
        )}
      </div>
    </Page>
  );
}
