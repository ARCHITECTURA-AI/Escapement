"use client";

import { CheckCircle2, XCircle } from "lucide-react";

export type Check = { id: string; name: string; passed: boolean; detail: string };

export function Checks({ checks }: { checks: Check[] }) {
  return (
    <ul className="divide-y divide-line">
      {checks.map((c) => (
        <li key={c.id} className="flex items-start gap-3 py-2.5 text-sm">
          {c.passed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good" aria-label="Passed" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-bad" aria-label="Failed" />}
          <span>
            <span className="text-ink">{c.name}</span>
            {c.detail && <span className="block text-xs text-muted">{c.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

