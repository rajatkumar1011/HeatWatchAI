/** Chart presentation helpers — shared recharts styling + time ticks. */
import { useMemo } from "react";
import type { ReactNode } from "react";

export const CHART_COLORS = {
  temperature: "#dc2626",
  heatIndex: "#f97316",
  severity: "#b91c1c",
  severityFill: "#fee2e2",
  alert: "#dc2626",
  positive: "#16a34a",
  neutral: "#94a3b8",
  negative: "#dc2626",
};

export function ChartTooltip({ active, payload, label, valueFormatter }: any & { valueFormatter?: (v: number, name: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-pop">
      <p className="mb-1 font-semibold text-slate-500">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey ?? p.name} className="tnum flex items-center gap-1.5 text-slate-700">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.stroke }} />
          {p.name}: {valueFormatter ? valueFormatter(p.value, String(p.name)) : String(p.value)}
        </p>
      ))}
    </div>
  );
}

/** Span-appropriate, non-repeating time ticks (fixes duplicated-label axes). */
export function useTimeTickFormatter(times: string[]): (iso: string) => string {
  const spanHours = useMemo(() => {
    if (times.length < 2) return 0;
    const a = new Date(times[0]).getTime();
    const b = new Date(times[times.length - 1]).getTime();
    return (b - a) / 3_600_000;
  }, [times]);

  return (iso: string) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    if (spanHours <= 36) {
      return d.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false });
    }
    // multi-day span: show day label, add hours only at day boundaries
    const day = d.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short" });
    const hour = d.getHours(); // locale-independent check for boundary is fine for ticks
    if (hour >= 9 && hour <= 12) return day;
    return day;
  };
}

export function useChartData<T>(rows: T[], timeKey: keyof T) {
  return useMemo(
    () => rows.map((r) => ({ ...r, _iso: String(r[timeKey]) })),
    [rows, timeKey],
  );
}

export function LegendDot({ color, label }: { color: string; label: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}
