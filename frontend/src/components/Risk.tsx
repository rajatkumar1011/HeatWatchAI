import type { RiskCategory } from "../types";
import { riskLabel } from "../utils/format";
import { Pill } from "./ui";

const RISK_STYLE: Record<RiskCategory, { className: string; dot: string }> = {
  low: { className: "border-green-200 bg-green-50 text-green-800", dot: "bg-green-500" },
  moderate: { className: "border-amber-200 bg-amber-50 text-amber-800", dot: "bg-amber-500" },
  high: { className: "border-red-200 bg-red-50 text-red-800", dot: "bg-red-500" },
};

export function RiskBadge({ category, score }: { category: RiskCategory; score?: number }) {
  const s = RISK_STYLE[category];
  return (
    <Pill
      text={riskLabel[category] + (typeof score === "number" ? ` · ${score.toFixed(0)}/100` : "")}
      className={s.className}
      dot={s.dot}
    />
  );
}

export function StatusPill({ text, className }: { text: string; className: string }) {
  return <Pill text={text} className={className} />;
}

/** Segmented 0–100 severity scale with documented thresholds (40 / 70). */
export function RiskScale({ score, category }: { score: number; category: RiskCategory }) {
  const clamped = Math.max(0, Math.min(100, score));
  const barColor =
    category === "high" ? "bg-red-600" : category === "moderate" ? "bg-amber-500" : "bg-green-600";
  return (
    <div className="w-full" role="img" aria-label={`Severity ${clamped.toFixed(0)} of 100, ${category} risk`}>
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-gradient-to-r from-green-200 via-amber-200 to-red-300">
        <div className={`absolute inset-y-0 left-0 rounded-full ${barColor}`} style={{ width: `${clamped}%` }} />
        {/* threshold markers at 40 (moderate) and 70 (high) */}
        <span className="absolute inset-y-0 left-[40%] w-px bg-white/90" aria-hidden />
        <span className="absolute inset-y-0 left-[70%] w-px bg-white/90" aria-hidden />
      </div>
      <div className="mt-1 flex justify-between text-[10px] font-medium text-slate-400">
        <span>0 · low</span>
        <span className="tnum">40 · moderate</span>
        <span className="tnum">70 · high</span>
        <span>100</span>
      </div>
    </div>
  );
}
