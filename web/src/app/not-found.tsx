import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-xl px-6 py-24 text-center">
      <div className="font-mono text-sm text-muted">UNKNOWN_TARGET</div>
      <h1 className="mt-3 font-serif text-4xl text-ink">You don&apos;t know of anything called that.</h1>
      <p className="mt-3 text-ink-2">The page you asked for does not exist, or it is not visible from here.</p>
      <Link href="/" className="mt-8 inline-flex h-10 items-center rounded-lg bg-ink px-4 text-sm font-medium text-paper">Back to the start</Link>
    </main>
  );
}
