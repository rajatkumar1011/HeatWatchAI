import type { DataMode, RiskCategory } from "../types";

/** All user-facing timestamps display in Asia/Kolkata (SRS FR-07). */
const TZ = "Asia/Kolkata";

export function formatTime(iso: string | null | undefined, withSeconds = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", {
    timeZone: TZ,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
    hour12: true,
  });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", { timeZone: TZ, day: "2-digit", month: "short", year: "numeric" });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export const riskColor: Record<RiskCategory, string> = {
  low: "#16a34a",
  moderate: "#d97706",
  high: "#dc2626",
};

export const riskBgClass: Record<RiskCategory, string> = {
  low: "bg-green-100 text-green-800 border-green-300",
  moderate: "bg-amber-100 text-amber-800 border-amber-300",
  high: "bg-red-100 text-red-800 border-red-300",
};

export const riskLabel: Record<RiskCategory, string> = {
  low: "Low Risk",
  moderate: "Moderate Risk",
  high: "High Risk",
};

/** Data provenance pill: demo data is always labelled, never passed off as live. */
export function modePill(mode: DataMode | undefined, freshness?: string): { text: string; className: string } | null {
  if (mode === "demo") return { text: "DEMO DATA", className: "bg-violet-100 text-violet-800 border-violet-300" };
  if (mode === "mixed") return { text: "MIXED SOURCES", className: "bg-slate-200 text-slate-700 border-slate-400" };
  if (freshness === "cached") return { text: "CACHED DATA", className: "bg-sky-100 text-sky-800 border-sky-300" };
  if (freshness === "live") return { text: "LIVE DATA", className: "bg-emerald-100 text-emerald-800 border-emerald-300" };
  return null;
}

export function sentimentEmoji(label: string): string {
  if (label === "positive") return "🙂";
  if (label === "negative") return "😟";
  return "😐";
}
