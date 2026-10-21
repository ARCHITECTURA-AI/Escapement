"use client";

import { Download, Eye, EyeOff, KeyRound, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, Button, Card, CardHeader, CodeBlock, Dialog, Notice, Page, PageHeader, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, relative } from "@/lib/format";
import { useApi, useMe } from "@/lib/hooks";

type Key = { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null };

export default function SettingsPage() {
  const { user, isLoading, mutate } = useMe();
  const router = useRouter();
  const keys = useApi<{ keys: Key[] }>(user ? "/api/v1/me/keys" : null);
  const [handle, setHandle] = useState("");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [keyName, setKeyName] = useState("");
  const [del, setDel] = useState(false);
  const [confirm, setConfirm] = useState("");

  useEffect(() => {
    if (!isLoading && !user) router.replace("/signin?next=/settings");
    if (user) {
      setHandle(user.handle);
      setName(user.display_name ?? "");
    }
  }, [user, isLoading, router]);
  if (!user) return <Page><Spinner /></Page>;

  const save = async (body: Record<string, unknown>) => {
    setSaving(true);
    setMsg(null);
    try {
      await api("/api/v1/me", { method: "PATCH", body });
      await mutate();
      setMsg({ tone: "good", text: "Saved." });
    } catch (e) {
      setMsg({ tone: "bad", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Page>
      <PageHeader eyebrow="Settings" title="Your account" lede="Escapement keeps only your GitHub email, a handle and your run data. Export or delete it here at any time." />
      {msg && <Notice tone={msg.tone} className="mb-6">{msg.text}</Notice>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Profile" />
          <form
            className="space-y-4 p-5"
            onSubmit={(e) => {
              e.preventDefault();
              save({ handle, display_name: name });
            }}
          >
            <label className="block text-sm">
              <span className="text-muted">Handle</span>
              <input value={handle} onChange={(e) => setHandle(e.target.value.toLowerCase())} className="mt-1 h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-ink" pattern="[a-z0-9][a-z0-9-]{1,38}" required />
            </label>
            <label className="block text-sm">
              <span className="text-muted">Display name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-ink" maxLength={80} />
            </label>
            <div className="text-sm text-muted">Email (from GitHub, never shown publicly): {user.email ?? "—"}</div>
            <Button type="submit" variant="primary" loading={saving}>Save profile</Button>
          </form>
        </Card>
        <Card>
          <CardHeader title="Privacy" />
          <div className="space-y-4 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="font-medium text-ink">Public profile</div>
                <p className="mt-0.5 text-sm text-muted">Off by default. When on, your agent versions, results and runs appear on your profile, on Watch and by name on leaderboards. When off, leaderboards show “Private agent”.</p>
              </div>
              <button
                role="switch"
                aria-checked={user.profile_public}
                onClick={() => save({ profile_public: !user.profile_public })}
                className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${user.profile_public ? "bg-good" : "bg-line-strong"}`}
              >
                <span className={`absolute top-1 size-5 rounded-full bg-white shadow transition-all ${user.profile_public ? "left-6" : "left-1"}`} />
                <span className="sr-only">Public profile</span>
              </button>
            </div>
            <Badge icon={user.profile_public ? <Eye className="size-3" aria-hidden /> : <EyeOff className="size-3" aria-hidden />}>{user.profile_public ? "Public" : "Private"}</Badge>
            <p className="text-sm text-muted">Certificates you share stay viewable by their link either way.</p>
          </div>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="API keys" subtitle="Keys are hashed at rest; only the prefix is stored in the clear." icon={<KeyRound className="size-4" aria-hidden />} />
          <div className="p-5">
            {newKey && <CodeBlock className="mb-4" code={newKey} label="new key: copy it now, it will not be shown again" />}
            <form
              className="mb-5 flex flex-wrap gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  const r = await api<{ key: string }>("/api/v1/me/keys", { body: { name: keyName || "default" } });
                  setNewKey(r.key);
                  setKeyName("");
                  keys.mutate();
                } catch (err) {
                  setMsg({ tone: "bad", text: err instanceof Error ? err.message : String(err) });
                }
              }}
            >
              <label className="sr-only" htmlFor="key-name">Key name</label>
              <input id="key-name" value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="Key name, e.g. laptop" className="h-10 min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink sm:max-w-xs" />
              <Button type="submit" variant="primary" icon={<KeyRound className="size-4" aria-hidden />}>Create key</Button>
            </form>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-[13px] text-muted"><tr><th className="py-2 font-medium">Name</th><th className="py-2 font-medium">Prefix</th><th className="py-2 font-medium">Created</th><th className="py-2 font-medium">Last used</th><th /></tr></thead>
                <tbody className="divide-y divide-line">
                  {keys.data?.keys.map((k) => (
                    <tr key={k.id} className={k.revoked_at ? "opacity-60" : ""}>
                      <td className="py-2.5 text-ink">{k.name}</td>
                      <td className="py-2.5 font-mono text-[13px]">{k.prefix}…</td>
                      <td className="py-2.5 text-muted">{dateTime(k.created_at)}</td>
                      <td className="py-2.5 text-muted">{k.last_used_at ? relative(k.last_used_at) : "never"}</td>
                      <td className="py-2.5 text-right">
                        {k.revoked_at ? (
                          <Badge>revoked</Badge>
                        ) : (
                          <Button size="sm" variant="ghost" onClick={async () => { await api(`/api/v1/me/keys/${k.id}`, { method: "DELETE" }); keys.mutate(); }}>Revoke</Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Your data" />
          <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="max-w-2xl text-sm text-ink-2">Export everything Escapement holds about you as JSON. Deleting your account unpublishes your profile, removes your replays and replaces your certificates with a revoked tombstone. Anonymous outcomes stay in season aggregates.</p>
            <div className="flex shrink-0 gap-2">
              <a href="/api/v1/me/export" className="inline-flex h-10 items-center gap-2 rounded-lg border border-line-strong bg-surface px-4 text-sm font-medium text-ink hover:bg-sunken"><Download className="size-4" aria-hidden />Export</a>
              <Button variant="danger" onClick={() => setDel(true)} icon={<Trash2 className="size-4" aria-hidden />}>Delete account</Button>
            </div>
          </div>
        </Card>
      </div>
      <Dialog
        open={del}
        onClose={() => setDel(false)}
        title="Delete your account?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDel(false)}>Cancel</Button>
            <Button
              variant="danger"
              disabled={confirm !== user.handle}
              onClick={async () => {
                await api("/api/v1/me/delete", { body: { confirm_handle: confirm } });
                await mutate();
                router.push("/");
              }}
            >
              Delete permanently
            </Button>
          </>
        }
      >
        <p>This cannot be undone. Type <span className="font-mono font-semibold text-ink">{user.handle}</span> to confirm.</p>
        <label className="sr-only" htmlFor="confirm-handle">Handle</label>
        <input id="confirm-handle" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="mt-3 h-10 w-full rounded-lg border border-line-strong bg-surface px-3 font-mono text-ink" autoComplete="off" />
      </Dialog>
    </Page>
  );
}
