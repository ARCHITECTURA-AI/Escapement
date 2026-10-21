"use client";

import clsx from "clsx";
import {
  AlertTriangle,
  Ban,
  Check,
  CheckCircle2,
  Copy,
  Flag,
  Hourglass,
  Loader2,
  MessageSquareQuote,
  ShieldCheck,
  Timer,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { type ButtonHTMLAttributes, type ReactNode, useEffect, useRef, useState } from "react";
import { endingLabel, shortHash } from "@/lib/format";

// ---------------------------------------------------------------- buttons

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "signal";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
};

const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed select-none whitespace-nowrap";
const buttonVariants = {
  primary: "bg-ink text-paper hover:bg-ink-2 shadow-sm",
  signal: "bg-signal text-white hover:opacity-90 shadow-sm dark:text-[#0e0e0c]",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-sunken",
  ghost: "text-ink-2 hover:bg-sunken",
  danger: "bg-bad text-white hover:opacity-90 dark:text-[#0e0e0c]",
};
const buttonSizes = { sm: "h-8 px-3 text-[13px]", md: "h-10 px-4 text-sm", lg: "h-12 px-6 text-[15px]" };

export function Button({ variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button className={clsx(buttonBase, buttonVariants[variant], buttonSizes[size], className)} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  icon,
  className,
  children,
  external,
}: {
  href: string;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
  external?: boolean;
}) {
  const cls = clsx(buttonBase, buttonVariants[variant ?? "secondary"], buttonSizes[size ?? "md"], className);
  if (external)
    return (
      <a href={href} className={cls} target="_blank" rel="noreferrer">
        {icon}
        {children}
      </a>
    );
  return (
    <Link href={href} className={cls}>
      {icon}
      {children}
    </Link>
  );
}

// ---------------------------------------------------------------- layout

export function Page({ children, className, wide }: { children: ReactNode; className?: string; wide?: boolean }) {
  return <main className={clsx("mx-auto w-full px-4 sm:px-6 pb-24 pt-8 sm:pt-12 animate-in", wide ? "max-w-[1400px]" : "max-w-6xl", className)}>{children}</main>;
}

export function PageHeader({ eyebrow, title, lede, actions, children }: { eyebrow?: ReactNode; title: ReactNode; lede?: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-8 sm:mb-10">
      {eyebrow && <div className="mb-3 text-[13px] font-medium uppercase tracking-[0.12em] text-muted">{eyebrow}</div>}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <h1 className="font-serif text-[2.2rem] leading-[1.08] text-ink sm:text-5xl">{title}</h1>
          {lede && <p className="mt-4 text-[17px] leading-relaxed text-ink-2">{lede}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  );
}

export function Card({ children, className, as: As = "section", ...rest }: { children: ReactNode; className?: string; as?: "section" | "div" | "article" } & Record<string, unknown>) {
  return (
    <As className={clsx("rounded-2xl border border-line bg-surface shadow-card", className)} {...rest}>
      {children}
    </As>
  );
}

export function CardHeader({ title, subtitle, actions, icon }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div className="flex min-w-0 items-start gap-3">
        {icon && <div className="mt-0.5 text-muted">{icon}</div>}
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex items-baseline justify-between gap-4">
      <h2 className="font-serif text-2xl text-ink sm:text-[1.75rem]">{children}</h2>
      {aside && <div className="text-sm text-muted">{aside}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- badges

type Tone = "neutral" | "signal" | "self" | "good" | "bad" | "warn";
const toneClass: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-2 border-line",
  signal: "bg-signal-soft text-signal-ink border-transparent",
  self: "bg-self-soft text-self border-dashed border-self/40",
  good: "bg-good-soft text-good border-transparent",
  bad: "bg-bad-soft text-bad border-transparent",
  warn: "bg-warn-soft text-warn border-transparent",
};

export function Badge({ tone = "neutral", icon, children, className, title }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium leading-5", toneClass[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

/** Every number says whether the server measured it or the client reported it (PRD 6). */
export function Source({ kind }: { kind: "server" | "self" | "attested" | "heuristic" }) {
  if (kind === "server")
    return (
      <Badge tone="signal" icon={<ShieldCheck className="size-3" aria-hidden />} title="Measured by the Escapement server">
        Server-measured
      </Badge>
    );
  if (kind === "attested")
    return (
      <Badge tone="signal" icon={<ShieldCheck className="size-3" aria-hidden />} title="First-party reference run: Escapement ran the model">
        Verified run
      </Badge>
    );
  if (kind === "heuristic")
    return (
      <Badge tone="warn" icon={<AlertTriangle className="size-3" aria-hidden />} title="A heuristic label, not ground truth">
        Heuristic
      </Badge>
    );
  return (
    <Badge tone="self" icon={<MessageSquareQuote className="size-3" aria-hidden />} title="Reported by the client and not verified">
      Self-reported
    </Badge>
  );
}

export function OutcomeBadge({ status, size = "sm" }: { status: string; size?: "sm" | "lg" }) {
  const map: Record<string, { tone: Tone; icon: ReactNode }> = {
    escaped: { tone: "good", icon: <CheckCircle2 className="size-3.5" aria-hidden /> },
    in_progress: { tone: "signal", icon: <span className="live-dot inline-block size-2 rounded-full bg-signal" aria-hidden /> },
    action_budget_exhausted: { tone: "bad", icon: <Hourglass className="size-3.5" aria-hidden /> },
    malformed_limit_reached: { tone: "bad", icon: <XCircle className="size-3.5" aria-hidden /> },
    idle_timeout: { tone: "warn", icon: <Timer className="size-3.5" aria-hidden /> },
    wall_clock_exceeded: { tone: "warn", icon: <Timer className="size-3.5" aria-hidden /> },
    client_aborted: { tone: "neutral", icon: <Flag className="size-3.5" aria-hidden /> },
    cancelled: { tone: "neutral", icon: <Ban className="size-3.5" aria-hidden /> },
    engine_error: { tone: "warn", icon: <AlertTriangle className="size-3.5" aria-hidden /> },
    reference_provider_failure: { tone: "warn", icon: <AlertTriangle className="size-3.5" aria-hidden /> },
  };
  const m = map[status] ?? { tone: "neutral" as Tone, icon: null };
  return (
    <Badge tone={m.tone} icon={m.icon} className={size === "lg" ? "px-3 py-1 text-sm" : undefined}>
      {endingLabel(status)}
    </Badge>
  );
}

// ---------------------------------------------------------------- data display

export function Stat({ label, value, sub, source, className }: { label: ReactNode; value: ReactNode; sub?: ReactNode; source?: "server" | "self" | "attested" | "heuristic"; className?: string }) {
  return (
    <div className={clsx("min-w-0", className)}>
      <div className="text-[13px] text-muted">{label}</div>
      <div className="mt-1 font-serif text-[1.7rem] leading-tight text-ink tabular">{value}</div>
      {sub && <div className="mt-0.5 text-[13px] text-muted">{sub}</div>}
      {source && <div className="mt-1.5"><Source kind={source} /></div>}
    </div>
  );
}

export function KV({ k, v, mono, source, stack }: { k: ReactNode; v: ReactNode; mono?: boolean; source?: "server" | "self" | "attested"; stack?: boolean }) {
  if (stack)
    return (
      <div className="border-b border-line py-2.5 text-sm last:border-0">
        <dt className="flex items-center gap-2 text-[13px] text-muted">
          {k}
          {source && <Source kind={source} />}
        </dt>
        <dd className={clsx("mt-0.5 min-w-0 break-words text-ink", mono && "font-mono text-[13px] break-all")}>{v}</dd>
      </div>
    );
  return (
    <div className="grid grid-cols-[minmax(0,10rem)_1fr] gap-3 border-b border-line py-2.5 text-sm last:border-0 sm:grid-cols-[13rem_1fr]">
      <dt className="text-muted">{k}</dt>
      <dd className={clsx("flex min-w-0 flex-wrap items-center gap-2 text-ink", mono && "font-mono text-[13px] break-all")}>
        {v}
        {source && <Source kind={source} />}
      </dd>
    </div>
  );
}

export function CopyButton({ value, label = "Copy", className }: { value: string; label?: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className={clsx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-muted hover:bg-sunken hover:text-ink", className)}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1400);
        } catch {
          /* clipboard unavailable */
        }
      }}
      aria-label={`${label}: ${value.slice(0, 24)}`}
    >
      {done ? <Check className="size-3.5 text-good" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
      <span>{done ? "Copied" : label}</span>
    </button>
  );
}

export function Hash({ value, n = 10, copy = true }: { value: string | null | undefined; n?: number; copy?: boolean }) {
  if (!value) return <span className="text-faint">—</span>;
  return (
    <span className="inline-flex items-center gap-1">
      <code className="font-mono text-[12.5px] text-ink-2" title={value}>
        {shortHash(value, n)}
      </code>
      {copy && <CopyButton value={value} label="Copy" />}
    </span>
  );
}

export function CodeBlock({ code, label, className }: { code: string; label?: string; className?: string }) {
  return (
    <div className={clsx("overflow-hidden rounded-xl border border-line bg-[#11110e] text-[#e9e7df] dark:bg-black/40", className)}>
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2 text-xs text-[#a8a59c]">
        <span>{label ?? "shell"}</span>
        <CopyButton value={code} className="text-[#a8a59c] hover:bg-white/10 hover:text-white" />
      </div>
      <pre className="overflow-x-auto px-4 py-3.5 font-mono text-[13px] leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/** A 95% interval with its point estimate on a 0–100% track. */
export function IntervalBar({ rate, lo, hi, className }: { rate: number | null; lo: number | null; hi: number | null; className?: string }) {
  if (rate === null || lo === null || hi === null) return <div className={clsx("h-2 rounded-full bg-sunken", className)} />;
  return (
    <div className={clsx("relative h-2 w-full rounded-full bg-sunken", className)} role="img" aria-label={`Estimate ${Math.floor(rate * 100)}%, interval ${Math.floor(lo * 100)} to ${Math.ceil(hi * 100)}%`}>
      <div className="absolute inset-y-0 rounded-full bg-signal/25" style={{ left: `${lo * 100}%`, width: `${Math.max(0.5, (hi - lo) * 100)}%` }} />
      <div className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-signal" style={{ left: `${rate * 100}%` }} />
    </div>
  );
}

export function Progress({ value, max, tone = "ink", label }: { value: number; max: number; tone?: "ink" | "warn" | "bad"; label?: string }) {
  const pct = Math.min(100, (value / Math.max(1, max)) * 100);
  const color = tone === "bad" ? "bg-bad" : tone === "warn" ? "bg-warn" : "bg-ink";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
      <div className={clsx("h-full rounded-full transition-[width] duration-300", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ---------------------------------------------------------------- tabs

export function Tabs<T extends string>({ value, onChange, items, className }: { value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[]; className?: string }) {
  return (
    <div role="tablist" className={clsx("inline-flex rounded-xl border border-line bg-sunken p-1", className)}>
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={clsx(
            "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
            value === it.value ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- feedback

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-lg bg-sunken", className)} />;
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line-strong px-6 py-12 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <div className="font-medium text-ink">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "neutral", icon, title, children, className }: { tone?: Tone; icon?: ReactNode; title?: ReactNode; children?: ReactNode; className?: string }) {
  const border = { neutral: "border-line", signal: "border-signal/30", self: "border-self/30", good: "border-good/30", bad: "border-bad/30", warn: "border-warn/30" }[tone];
  return (
    <div className={clsx("flex gap-3 rounded-xl border px-4 py-3 text-sm", toneClass[tone], border, className)} role={tone === "bad" ? "alert" : undefined}>
      {icon && <div className="mt-0.5 shrink-0">{icon}</div>}
      <div className="min-w-0 text-ink-2">
        {title && <div className="font-medium text-ink">{title}</div>}
        {children && <div className={title ? "mt-0.5" : undefined}>{children}</div>}
      </div>
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <Notice tone="bad" icon={<AlertTriangle className="size-4" aria-hidden />} title="Could not load this">
      <span>{message}</span>
      {retry && (
        <button className="ml-2 underline underline-offset-2" onClick={retry}>
          Try again
        </button>
      )}
    </Notice>
  );
}

// ---------------------------------------------------------------- dialog

export function Dialog({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const focusables = () => Array.from(node?.querySelectorAll<HTMLElement>("button, [href], input, textarea, select, [tabindex]:not([tabindex='-1'])") ?? []);
    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const els = focusables();
        if (!els.length) return;
        const first = els[0];
        const last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center" role="presentation">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined} className="relative w-full max-w-md animate-in rounded-2xl border border-line bg-surface shadow-card">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="font-semibold text-ink">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-sunken hover:text-ink" aria-label="Close">
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="px-5 py-4 text-sm text-ink-2">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-line-strong bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-ink-2">{children}</kbd>;
}

export function useCountdown(target: string | null | undefined): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!target) return "—";
  const diff = Math.max(0, new Date(target).getTime() - now);
  const h = Math.floor(diff / 3_600_000);
  const m = Math.floor((diff % 3_600_000) / 60_000);
  const s = Math.floor((diff % 60_000) / 1000);
  if (h >= 48) return `${Math.floor(h / 24)} days`;
  return `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
}
