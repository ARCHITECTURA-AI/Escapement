"use client";

import clsx from "clsx";
import { ChevronDown, FlaskConical, LogOut, Menu, Moon, Settings, Sun, User, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useMe, useMeta } from "@/lib/hooks";
import { Wordmark } from "./logo";
import { ButtonLink } from "./ui";

const NAV = [
  { href: "/play", label: "Play" },
  { href: "/enter", label: "Enter" },
  { href: "/watch", label: "Watch" },
  { href: "/compare", label: "Compare" },
  { href: "/daily", label: "Daily" },
  { href: "/seasons", label: "Seasons" },
  { href: "/profile", label: "Profile" },
  { href: "/methodology", label: "Methodology" },
];

const LAB = [
  { href: "/lab/generate", label: "Generate" },
  { href: "/lab/validate", label: "Validate" },
  { href: "/lab/jobs", label: "Jobs" },
];

export function ThemeToggle() {
  const [theme, setTheme] = useState<string | null>(null);
  useEffect(() => setTheme(document.documentElement.dataset.theme ?? "light"), []);
  const flip = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("esc-theme", next);
    } catch {}
    setTheme(next);
  };
  return (
    <button onClick={flip} className="rounded-lg p-2 text-muted hover:bg-sunken hover:text-ink" aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
      {theme === "dark" ? <Sun className="size-[18px]" aria-hidden /> : <Moon className="size-[18px]" aria-hidden />}
    </button>
  );
}

function UserMenu() {
  const { user, mutate } = useMe();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  if (!user)
    return (
      <ButtonLink href={`/signin?next=${encodeURIComponent(pathname)}`} variant="primary" size="sm">
        Sign in
      </ButtonLink>
    );
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 hover:bg-sunken" aria-haspopup="menu" aria-expanded={open}>
        {user.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={user.avatar_url} alt="" className="size-7 rounded-full border border-line" />
        ) : (
          <span className="grid size-7 place-items-center rounded-full bg-sunken text-xs font-semibold text-ink-2">{user.handle.slice(0, 2).toUpperCase()}</span>
        )}
        <span className="hidden text-sm font-medium text-ink lg:inline">{user.handle}</span>
        <ChevronDown className="size-3.5 text-muted" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-2 w-56 animate-in overflow-hidden rounded-xl border border-line bg-surface p-1 shadow-card">
          <div className="px-3 py-2 text-xs text-muted">Signed in as <span className="font-medium text-ink">{user.handle}</span></div>
          <Link role="menuitem" href={`/u/${user.handle}`} onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink hover:bg-sunken">
            <User className="size-4 text-muted" aria-hidden /> Your profile
          </Link>
          <Link role="menuitem" href="/settings" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink hover:bg-sunken">
            <Settings className="size-4 text-muted" aria-hidden /> Settings and API keys
          </Link>
          <button
            role="menuitem"
            onClick={async () => {
              await api("/api/v1/auth/logout", { method: "POST", body: {} });
              await mutate();
              setOpen(false);
              router.push("/");
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-ink hover:bg-sunken"
          >
            <LogOut className="size-4 text-muted" aria-hidden /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function Nav() {
  const pathname = usePathname();
  const meta = useMeta();
  const [mobile, setMobile] = useState(false);
  const local = meta?.mode === "local";
  useEffect(() => setMobile(false), [pathname]);
  const active = (href: string) => pathname === href || pathname.startsWith(href + "/");
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur supports-[backdrop-filter]:bg-paper/75">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-6 px-4 sm:px-6">
        <Link href="/" aria-label="Escapement home" className="shrink-0">
          <Wordmark />
        </Link>
        <nav aria-label="Main" className="hidden flex-1 items-center gap-0.5 xl:flex">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={active(n.href) ? "page" : undefined}
              className={clsx(
                "rounded-lg px-3 py-2 text-sm transition-colors",
                active(n.href) ? "bg-sunken font-medium text-ink" : "text-muted hover:bg-sunken hover:text-ink",
              )}
            >
              {n.label}
            </Link>
          ))}
          {local && (
            <div className="ml-2 flex items-center gap-0.5 border-l border-line pl-2">
              <FlaskConical className="mr-1 size-4 text-faint" aria-label="Local research mode" />
              {LAB.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={active(n.href) ? "page" : undefined}
                  className={clsx("rounded-lg px-2.5 py-2 text-sm", active(n.href) ? "bg-sunken font-medium text-ink" : "text-muted hover:bg-sunken hover:text-ink")}
                >
                  {n.label}
                </Link>
              ))}
            </div>
          )}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <UserMenu />
          <button className="rounded-lg p-2 text-ink xl:hidden" onClick={() => setMobile((m) => !m)} aria-label="Menu" aria-expanded={mobile}>
            {mobile ? <X className="size-5" aria-hidden /> : <Menu className="size-5" aria-hidden />}
          </button>
        </div>
      </div>
      {mobile && (
        <nav aria-label="Main" className="animate-in border-t border-line bg-paper px-4 pb-4 pt-2 xl:hidden">
          <div className="grid grid-cols-2 gap-1">
            {[...NAV, ...(local ? LAB : [])].map((n) => (
              <Link key={n.href} href={n.href} className={clsx("rounded-lg px-3 py-2.5 text-[15px]", active(n.href) ? "bg-sunken font-medium text-ink" : "text-ink-2")}>
                {n.label}
              </Link>
            ))}
          </div>
        </nav>
      )}
    </header>
  );
}

export function Footer() {
  const meta = useMeta();
  return (
    <footer className="border-t border-line">
      <div className="mx-auto grid max-w-[1400px] gap-8 px-4 py-10 text-sm text-muted sm:grid-cols-[1.4fr_1fr_1fr_1fr] sm:px-6">
        <div>
          <Wordmark />
          <p className="mt-3 max-w-sm leading-relaxed">
            A verifiable, replayable, bring-your-own-agent arena with signed records. Escapement is one signal among several: it does not promise anyone a job.
          </p>
        </div>
        <div>
          <div className="mb-2 font-medium text-ink">Arena</div>
          <ul className="space-y-1.5">
            <li><Link href="/play" className="hover:text-ink">Play Practice</Link></li>
            <li><Link href="/daily" className="hover:text-ink">Daily Room</Link></li>
            <li><Link href="/seasons" className="hover:text-ink">Seasons</Link></li>
            <li><Link href="/watch" className="hover:text-ink">Watch runs</Link></li>
          </ul>
        </div>
        <div>
          <div className="mb-2 font-medium text-ink">Build</div>
          <ul className="space-y-1.5">
            <li><Link href="/enter" className="hover:text-ink">Enter your agent</Link></li>
            <li><Link href="/methodology" className="hover:text-ink">Methodology</Link></li>
            <li><a href="/api/docs" className="hover:text-ink">API reference</a></li>
            <li><a href="/.well-known/escapement-keys.json" className="hover:text-ink">Signing keys</a></li>
          </ul>
        </div>
        <div>
          <div className="mb-2 font-medium text-ink">Project</div>
          <ul className="space-y-1.5">
            <li><a href="https://github.com/architectura-ai/escapement" className="hover:text-ink">Source (Apache-2.0)</a></li>
            <li><Link href="/methodology#privacy" className="hover:text-ink">Privacy</Link></li>
            <li><Link href="/methodology#support" className="hover:text-ink">Support</Link></li>
          </ul>
          {meta && (
            <p className="mt-4 font-mono text-xs text-faint">
              engine {meta.engine_version} · protocol {meta.protocol_version} · {meta.mode} mode
            </p>
          )}
        </div>
      </div>
    </footer>
  );
}
