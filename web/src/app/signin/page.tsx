"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { LogoMark } from "@/components/logo";
import { Button, Card, Notice, Page } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe, useMeta } from "@/lib/hooks";

function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" className="size-5" fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

const ERRORS: Record<string, string> = {
  state: "The sign-in link expired or was opened in another browser. Try again.",
  github: "GitHub did not complete the sign-in. Try again.",
  deleted: "That account was deleted.",
};

function SignIn() {
  const params = useSearchParams();
  const next = params.get("next") ?? "/";
  const meta = useMeta();
  const { mutate } = useMe();
  const router = useRouter();
  const [handle, setHandle] = useState("local");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(params.get("error") ? ERRORS[params.get("error")!] ?? "Sign-in failed." : null);
  return (
    <Page className="max-w-md">
      <Card className="p-8">
        <LogoMark className="size-10 text-ink" />
        <h1 className="mt-5 font-serif text-3xl text-ink">Sign in to Escapement</h1>
        <p className="mt-2 text-sm text-ink-2">Sign in to get certificates, API keys and a profile. Practice is open without an account.</p>
        {err && <Notice tone="bad" className="mt-5">{err}</Notice>}
        <div className="mt-6 space-y-3">
          {meta?.github_login && (
            <a href={`/api/v1/auth/github/login?next=${encodeURIComponent(next)}`} className="flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-ink text-[15px] font-medium text-paper hover:bg-ink-2">
              <GitHubMark /> Continue with GitHub
            </a>
          )}
          {meta?.local_login && (
            <form
              className="space-y-2"
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setErr(null);
                try {
                  await api("/api/v1/auth/local", { body: { handle } });
                  await mutate();
                  router.push(next);
                } catch (e2) {
                  setErr(e2 instanceof Error ? e2.message : String(e2));
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label className="block text-sm">
                <span className="text-muted">Local research mode: pick a handle</span>
                <input value={handle} onChange={(e) => setHandle(e.target.value.toLowerCase())} className="mt-1 h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-ink" />
              </label>
              <Button type="submit" variant={meta.github_login ? "secondary" : "primary"} size="lg" className="w-full" loading={busy}>Sign in locally</Button>
            </form>
          )}
          {meta && !meta.github_login && !meta.local_login && <Notice tone="warn">GitHub sign-in is not configured on this server.</Notice>}
        </div>
        <p className="mt-6 text-xs leading-relaxed text-muted">GitHub only: no passwords and no email links. We store your GitHub email, a handle and your run data, nothing else, and you can export or delete it any time.</p>
      </Card>
    </Page>
  );
}

export default function SignInPage() {
  return (
    <Suspense>
      <SignIn />
    </Suspense>
  );
}
