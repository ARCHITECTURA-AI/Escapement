import type { Metadata } from "next";
import { CertificateView } from "./view";

const API = process.env.ESCAPEMENT_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  try {
    const res = await fetch(`${API}/api/v1/certificates/${id}`, { cache: "no-store" });
    if (!res.ok) return { title: "Run Certificate" };
    const data = await res.json();
    const c = data.certificate;
    if (c.tombstone) return { title: "Revoked certificate" };
    const who = c.agent.agent_type === "human" ? "A human player" : `${c.agent.name} ${c.agent.version ?? ""}`.trim();
    const outcome = c.outcome === "escaped" ? "escaped" : `ended (${String(c.outcome).replaceAll("_", " ")})`;
    const title = `${who} ${outcome} ${c.room.title} in ${c.actions_used}/${c.action_budget} actions`;
    return {
      title,
      description: "A signed Escapement Run Certificate: hash-chained, replayable and verifiable offline. It certifies the actions, not who chose them.",
      openGraph: { title, description: "Signed Run Certificate · Escapement" },
    };
  } catch {
    return { title: "Run Certificate" };
  }
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CertificateView id={id} />;
}
