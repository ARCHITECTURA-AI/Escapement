import type { Action } from "./types";

export const ENDINGS: Record<string, string> = {
  in_progress: "In progress",
  escaped: "Escaped",
  action_budget_exhausted: "Budget exhausted",
  malformed_limit_reached: "Malformed limit",
  idle_timeout: "Idle timeout",
  wall_clock_exceeded: "Wall clock exceeded",
  client_aborted: "Ended by client",
  cancelled: "Cancelled",
  engine_error: "Engine error",
  reference_provider_failure: "Provider failure",
};

export function endingLabel(status: string): string {
  return ENDINGS[status] ?? status.replaceAll("_", " ");
}

// Rates are rounded down and intervals rounded outward, never flattering (14.4).
export function pct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined) return "—";
  const f = 10 ** digits;
  return `${(Math.floor(x * 100 * f + 1e-9) / f).toFixed(digits)}%`;
}

export function pctCeil(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined) return "—";
  const f = 10 ** digits;
  return `${(Math.ceil(x * 100 * f - 1e-9) / f).toFixed(digits)}%`;
}

export function interval(lo: number | null | undefined, hi: number | null | undefined): string {
  if (lo === null || lo === undefined || hi === null || hi === undefined) return "—";
  return `${pct(lo)}–${pctCeil(hi)}`;
}

export function shortHash(h: string | null | undefined, n = 10): string {
  if (!h) return "—";
  return `${h.slice(0, n)}…${h.slice(-4)}`;
}

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(Math.floor(ms / 100) / 10).toFixed(1)}s`;
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function date(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const abs = Math.abs(diff);
  const fmt = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (abs < 60) return fmt.format(-Math.round(diff), "second");
  if (abs < 3600) return fmt.format(-Math.round(diff / 60), "minute");
  if (abs < 86400) return fmt.format(-Math.round(diff / 3600), "hour");
  return fmt.format(-Math.round(diff / 86400), "day");
}

export function usd(micros: number | null | undefined): string {
  if (micros === null || micros === undefined) return "—";
  const v = micros / 1_000_000;
  return v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;
}

export function actionText(action: Action | null | undefined): string {
  if (!action) return "—";
  if (action.tool === "system.end") return `run ended (${(action.arguments?.ending ?? "").replaceAll("_", " ")})`;
  if (action.malformed) return `${action.tool ?? "?"}(…) — malformed`;
  const args = action.arguments ?? {};
  const vals = Object.values(args);
  return `${action.tool}(${vals.join(", ")})`;
}

export function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
