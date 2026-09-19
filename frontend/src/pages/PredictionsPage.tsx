import { useCallback, useEffect, useMemo, useState } from "react";
import { Line, LineChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "../api/client";
import type { Location, Prediction, RiskCategory } from "../types";
import { Button, Card, EmptyState, ErrorState, MetricTile, PageHeader, Pill, Select, Skeleton, useToast } from "../components/ui";
import { RiskBadge, RiskScale } from "../components/Risk";
import { CHART_COLORS, ChartTooltip, useTimeTickFormatter } from "../components/charts";
import { BrainIcon, ChevronDownIcon, ClockIcon, GaugeIcon, RefreshIcon } from "../components/icons";
import { formatTime, relativeTime } from "../utils/format";

export function PredictionsPage() {
  const toast = useToast();
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<number | null>(null);
  const [history, setHistory] = useState<Prediction[]>([]);
  const [latest, setLatest] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showTechnical, setShowTechnical] = useState(false);

  useEffect(() => {
    api
      .get<{ data: Location[] }>("/locations?monitored=true")
      .then((r) => {
        setLocations(r.data.data);
        if (r.data.data.length) setLocationId(r.data.data[0].id);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  const load = useCallback(async () => {
    if (!locationId) return;
    setLoading(true);
    try {
      const [h, l] = await Promise.all([
        api.get(`/predictions/history?location_id=${locationId}&days=14`),
        api.get(`/predictions/latest?location_id=${locationId}`),
      ]);
      setHistory(h.data.data);
      setLatest(l.data.data.available === false ? null : l.data.data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [locationId]);

  useEffect(() => {
    load();
  }, [load]);

  const run = async () => {
    setBusy(true);
    try {
      await api.post("/predictions/run", { location_id: locationId });
      await load();
      toast("success", "Severity assessment updated.");
    } catch (err) {
      toast("error", errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const factors: string[] = useMemo(
    () => (latest?.contributing_factors ? JSON.parse(latest.contributing_factors) : []),
    [latest],
  );

  const tickFormatter = useTimeTickFormatter(history.map((p) => p.predicted_at));

  const inputs = useMemo(() => {
    if (!latest?.inputs) return null;
    try {
      return JSON.parse(latest.inputs);
    } catch {
      return null;
    }
  }, [latest]);

  return (
    <div>
      <PageHeader
        title="Heatwave Predictions"
        description="Weather-based severity model combined with a documented, bounded sentiment-fusion layer. Human-readable results first; full technical provenance stays available below."
      >
        <div className="w-48">
          <Select
            ariaLabel="Location"
            value={locationId ?? ""}
            onChange={(v) => setLocationId(Number(v))}
            options={locations.map((l) => ({ value: l.id, label: l.display_name }))}
          />
        </div>
        <Button
          onClick={run}
          disabled={busy}
          icon={<RefreshIcon className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />}
        >
          Run prediction
        </Button>
      </PageHeader>

      {loading && !latest ? (
        <div className="space-y-4">
          <div className="hw-skeleton h-44 rounded-xl" />
          <div className="hw-skeleton h-56 rounded-xl" />
        </div>
      ) : error && !latest ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <div className="space-y-4">
          {latest && (
            <section
              className={`overflow-hidden rounded-xl border bg-white shadow-card ${
                latest.risk_category === "high"
                  ? "border-red-200"
                  : latest.risk_category === "moderate"
                    ? "border-amber-200"
                    : "border-green-200"
              }`}
            >
              <div className="flex flex-col gap-5 p-5 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <RiskBadge category={latest.risk_category as RiskCategory} />
                    <Pill
                      text={latest.data_mode === "demo" ? "DEMO DATA" : latest.data_mode.toUpperCase()}
                      className={
                        latest.data_mode === "demo"
                          ? "border-violet-200 bg-violet-50 text-violet-700"
                          : "border-emerald-200 bg-emerald-50 text-emerald-700"
                      }
                    />
                  </div>
                  <div className="mt-3 flex items-center gap-3">
                    <p className="tnum text-4xl font-semibold tracking-tight text-slate-900">
                      {latest.severity_score.toFixed(0)}
                      <span className="text-base font-medium text-slate-400">/100 severity</span>
                    </p>
                  </div>
                  <div className="mt-3 max-w-md">
                    <RiskScale score={latest.severity_score} category={latest.risk_category as RiskCategory} />
                  </div>
                  <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-500">
                    <ClockIcon className="h-3.5 w-3.5 text-slate-400" />
                    Assessed {formatTime(latest.predicted_at)} ({relativeTime(latest.predicted_at)})
                  </p>
                </div>

                <div className="grid shrink-0 grid-cols-2 gap-x-8 gap-y-3 md:border-l md:border-slate-100 md:pl-6">
                  <MetricTile label="Weather model" value={`${latest.weather_model_risk?.toFixed(0) ?? "—"}/100`} icon={<GaugeIcon className="h-4 w-4" />} />
                  <MetricTile
                    label="Sentiment fusion"
                    value={`+${latest.sentiment_adjustment ?? 0}`}
                    sub="bounded · upward-only"
                    icon={<BrainIcon className="h-4 w-4" />}
                  />
                  <div className="col-span-2 text-xs text-slate-500">
                    {latest.confidence != null ? (
                      <>
                        Confidence{" "}
                        <span className="tnum font-semibold text-slate-700">{latest.confidence.toFixed(0)}%</span>{" "}
                        — weather-model class probability.
                      </>
                    ) : (
                      "Rule-based method — no statistical confidence available."
                    )}
                  </div>
                </div>
              </div>

              {/* Human-readable contributing factors */}
              {factors.length > 0 && (
                <div className="border-t border-slate-100 bg-slate-50/60 px-5 py-3.5">
                  <p className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400">Why this assessment</p>
                  <ul className="mt-1.5 grid gap-1 text-xs leading-relaxed text-slate-600 md:grid-cols-2">
                    {factors.map((f, i) => (
                      <li key={i} className="flex gap-1.5">
                        <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-slate-400" aria-hidden />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Technical provenance — collapsible, never removed */}
              <div className="border-t border-slate-100 px-5 py-3">
                <button
                  onClick={() => setShowTechnical((v) => !v)}
                  aria-expanded={showTechnical}
                  className="flex w-full items-center justify-between text-xs font-semibold text-slate-500 hover:text-slate-700"
                >
                  Technical details & methodology (audit)
                  <ChevronDownIcon className={`h-4 w-4 transition-transform ${showTechnical ? "rotate-180" : ""}`} />
                </button>
                {showTechnical && (
                  <dl className="mt-3 grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
                    <div className="rounded-lg bg-slate-50 p-3">
                      <dt className="font-bold uppercase tracking-wide text-slate-400">Methodology</dt>
                      <dd className="mt-1 break-words text-slate-600">{latest.methodology}</dd>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3">
                      <dt className="font-bold uppercase tracking-wide text-slate-400">Model version</dt>
                      <dd className="mt-1 text-slate-600">{latest.model_version}</dd>
                      <dt className="mt-2 font-bold uppercase tracking-wide text-slate-400">Prediction ID</dt>
                      <dd className="tnum mt-1 text-slate-600">#{latest.id}</dd>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3">
                      <dt className="font-bold uppercase tracking-wide text-slate-400">Inputs used</dt>
                      <dd className="mt-1 space-y-0.5 text-slate-600">
                        <p>Weather obs: #{latest.weather_observation_id ?? "—"}</p>
                        <p>Sentiment aggregate: #{latest.sentiment_aggregate_id ?? "—"}</p>
                        {inputs?.weather && (
                          <p className="tnum">
                            {inputs.weather.temperature_c}°C · {inputs.weather.humidity_pct}% RH · HI{" "}
                            {inputs.weather.heat_index_c ?? "n/a"}
                          </p>
                        )}
                      </dd>
                    </div>
                  </dl>
                )}
              </div>
            </section>
          )}

          <Card title="Severity history" subtitle="14 days · dotted lines mark the moderate (40) and high (70) thresholds" bodyClassName="p-3">
            {history.length >= 2 ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={history} margin={{ top: 8, right: 12, left: -22, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="predicted_at"
                    tickFormatter={tickFormatter}
                    tick={{ fontSize: 10 }}
                    tickLine={false}
                    axisLine={{ stroke: "#e2e8f0" }}
                    minTickGap={48}
                    interval="preserveStartEnd"
                  />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={38} />
                  <Tooltip content={<ChartTooltip valueFormatter={(v: number) => `${Number(v).toFixed(0)}/100`} />} />
                  <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="4 3" strokeOpacity={0.55} />
                  <ReferenceLine y={40} stroke="#d97706" strokeDasharray="4 3" strokeOpacity={0.55} />
                  <Line
                    type="stepAfter"
                    dataKey="severity_score"
                    name="Fused severity"
                    stroke={CHART_COLORS.severity}
                    strokeWidth={1.8}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState compact title="Not enough prediction history" hint="Run predictions over several days to build the trend." />
            )}
          </Card>

          <Card title="Assessment records" bodyClassName="p-0">
            {loading ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : history.length === 0 ? (
              <div className="p-4">
                <EmptyState compact title="No predictions stored" hint="Run a prediction to begin." />
              </div>
            ) : (
              <div className="max-h-[420px] overflow-auto">
                <table className="w-full text-left text-[13px]">
                  <thead className="sticky top-0 bg-slate-50/95 text-[10.5px] uppercase tracking-wider text-slate-500 backdrop-blur">
                    <tr>
                      <th className="px-3.5 py-2.5 font-semibold">Assessed (IST)</th>
                      <th className="px-3.5 py-2.5 font-semibold">Risk</th>
                      <th className="px-3.5 py-2.5 text-right font-semibold">Score</th>
                      <th className="px-3.5 py-2.5 text-right font-semibold">Weather</th>
                      <th className="px-3.5 py-2.5 text-right font-semibold">Sentiment</th>
                      <th className="px-3.5 py-2.5 font-semibold">Provenance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {[...history].reverse().slice(0, 100).map((p) => (
                      <tr key={p.id} className="transition-colors hover:bg-slate-50/80">
                        <td className="tnum whitespace-nowrap px-3.5 py-2 font-medium text-slate-700">
                          {formatTime(p.predicted_at)}
                        </td>
                        <td className="px-3.5 py-2">
                          <RiskBadge category={p.risk_category as RiskCategory} />
                        </td>
                        <td className="tnum px-3.5 py-2 text-right font-semibold text-slate-800">
                          {p.severity_score.toFixed(0)}
                        </td>
                        <td className="tnum px-3.5 py-2 text-right text-slate-600">
                          {p.weather_model_risk?.toFixed(0) ?? "—"}
                        </td>
                        <td className="tnum px-3.5 py-2 text-right text-slate-600">
                          {p.sentiment_adjustment != null ? `+${p.sentiment_adjustment.toFixed(1)}` : "—"}
                        </td>
                        <td className="px-3.5 py-2">
                          <Pill
                            text={p.data_mode.toUpperCase()}
                            className={
                              p.data_mode === "demo"
                                ? "border-violet-200 bg-violet-50 text-violet-700"
                                : "border-emerald-200 bg-emerald-50 text-emerald-700"
                            }
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
