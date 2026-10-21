export function LogoMark({ className = "size-6" }: { className?: string }) {
  // A sealed room with its door open and a path leading out.
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden fill="none">
      <rect x="3.5" y="3.5" width="25" height="25" rx="6" stroke="currentColor" strokeWidth="2.25" />
      <path d="M21 12.5v7" stroke="var(--paper)" strokeWidth="5" />
      <path d="M11 16h14.5m0 0-4-4m4 4-4 4" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="10" cy="16" r="2.4" fill="currentColor" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2 text-ink">
      <LogoMark className="size-[26px]" />
      <span className="font-serif text-[1.35rem] leading-none tracking-[-0.02em]">Escapement</span>
    </span>
  );
}
