import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, downloadFile, errorMessage } from "../api/client";
import type { DashboardPayload, Location, RiskCategory } from "../types";
import { Button, Card, EmptyState, ErrorState, MetricTile, Pill, Select, Skeleton, useToast } from "../components/ui";
import { RiskBadge, RiskScale, StatusPill } from "../components/Risk";
import { CHART_COLORS, ChartTooltip, useTimeTickFormatter } from "../components/charts";
import {
  AlertTriangleIcon,
  BrainIcon,
  ChatIcon,
  ClockIcon,
  DownloadIcon,
  DropIcon,
  HeatIcon,
  PhoneIcon,
  PinIcon,
  RefreshIcon,
  TempIcon,
  WindIcon,
} from "../components/icons";
import { formatTime, modePill, relativeTime } from "../utils/format";

/* --------------------------------------------------------------- helpers */

type FeedPost = DashboardPayload["posts"][number];

function dedupePosts(posts: FeedPost[]): FeedPost[] {
  const seen = new Set<string>();
  const out: FeedPost[] = [];
  for (const p of posts) {
    const key = p.text.trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  return out.sort((a, b) => {
    const ra = (a.sentiment?.distress_flag ? 2 : 0) + (a.sentiment?.is_heat_related ? 1 : 0);
    const rb = (b.sentiment?.distress_flag ? 2 : 0) + (b.sentiment?.is_heat_related ? 1 : 0);
    if (rb !== ra) return rb - ra; // distress → heat-related → rest
    return new Date(b.published_at).getTime() - new Date(a.published_at).getTime();
  });
}

function postSentimentPill(sentiment: NonNullable<DashboardPayload["posts"][number]["sentiment"]>) {
  if (sentiment.label === "negative")
    return { text: `Negative ${sentiment.score.toFixed(2)}`, className: "border-red-200 bg-red-50 text-red-700" };
  if (sentiment.label === "positive")
    return { text: `Positive +${sentiment.score.toFixed(2)}`, className: "border-green-200 bg-green-50 text-green-700" };
  return { text: "Neutral", className: "border-slate-200 bg-slate-50 text-slate-600" };
}

/* ------------------------------------------------------------------ page */

export function DashboardPage() {
  const toast = useToast();
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<number | null>(null);
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const didInitialToast = useRef(false);

  useEffect(() => {
    api
      .get<{ data: Location[] }>("/locations?monitored=true")
      .then((r) => {
        setLocations(r.data.data);
        if (r.data.data.length) setLocationId((prev) => prev ?? r.data.data[0].id);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  const load = useCallback(async () => {
    if (!locationId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await api.get<{ data: DashboardPayload }>(`/dashboard?location_id=${locationId}`);
      setData(r.data.data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [locationId]);

  useEffect(() => {
    load();
  }, [load]);

  // Light polling — dashboard reflects new data without hammering the API.
  useEffect(() => {
    const t = setInterval(load, 120000);
    return () => clearInterval(t);
  }, [load]);

  const refreshNow = async () => {
    setBusyAction("refresh");
    try {
      await api.post("/weather/refresh", { location_id: locationId });
      await load();
      toast("success", "Monitoring pipeline refreshed.");
    } catch (err) {
      toast("error", errorMessage(err));
    } finally {
      setBusyAction(null);
    }
  };

  const generateReport = async (format: "pdf" | "csv") => {
    setBusyAction(format);
    try {
      const end = new Date();
      const start = new Date(end.getTime() - 7 * 864e5);
      const iso = (d: Date) => d.toISOString().slice(0, 10);
      const r = await api.post("/reports/generate", {
        location_id: locationId,
        start_date: iso(start),
        end_date: iso(end),
        format,
      });
      await downloadFile(`/reports/${r.data.data.id}/download`);
      toast("success", `${format.toUpperCase()} report generated and downloaded.`);
    } catch (err) {
      toast("error", `Report failed: ${errorMessage(err)}`);
    } finally {
      setBusyAction(null);
    }
  };

  const weatherPill = useMemo(() => {
    if (!data?.weather || data.weather.available === false) return null;
    return modePill(data.weather.data_mode, data.weather.freshness);
  }, [data]);

  const posts = useMemo(() => (data ? dedupePosts(data.posts ?? []).slice(0, 7) : []), [data]);

  const wSeries = data?.series.weather ?? [];
  const timeTicks = useMemo(() => wSeries.map((o) => o.observed_at), [wSeries]);
  const tickFormatter = useTimeTickFormatter(timeTicks);

  const severitySeries = data?.series.predictions ?? [];
  const severityFormatter = useTimeTickFormatter(severitySeries.map((p) => p.predicted_at));

  const sentimentPie = useMemo(() => {
    const s = data?.sentiment;
    if (!s?.available || !s.post_count) return [];
    return [
      { name: "Positive", value: s.positive_count, color: CHART_COLORS.positive },
      { name: "Neutral", value: s.neutral_count, color: CHART_COLORS.neutral },
      { name: "Negative", value: s.negative_count, color: CHART_COLORS.negative },
    ].filter((d) => d.value > 0);
  }, [data]);

  if (error && !data) {
    return (
      <>
        <Skeleton className="h-9 w-72" />
        <div className="mt-4">
          <ErrorState message={error} onRetry={load} />
        </div>
      </>
    );
  }

  const w = data?.weather;
  const p = data?.prediction as DashboardPayload["prediction"];
  const hasPrediction = p && "risk_category" in p && p.available !== false;
  const s = data?.sentiment;
  const hiAvailable = w?.heat_index_c != null;
  const activeAlerts = data?.alerts.filter((a) => a.status === "active") ?? [];

  return (
    <div className="space-y-4">
      {/* ---- Heading row: title, location, freshness, actions ---- */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Operations Dashboard</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Current conditions, AI risk assessment, and public distress signals for{" "}
            <span className="font-semibold text-slate-700">{data?.location.display_name ?? "…"}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="w-48">
            <Select
              ariaLabel="Location selection"
              value={locationId ?? ""}
              onChange={(v) => setLocationId(Number(v))}
              options={locations.map((l) => ({ value: l.id, label: l.display_name }))}
            />
          </div>
          {weatherPill && <StatusPill text={weatherPill.text} className={weatherPill.className} />}
          <Button
            variant="secondary"
            onClick={refreshNow}
            disabled={busyAction === "refresh"}
            icon={<RefreshIcon className={`h-4 w-4 ${busyAction === "refresh" ? "animate-spin" : ""}`} />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {loading && !data ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="space-y-4 xl:col-span-2">
            <div className="hw-skeleton h-40 rounded-xl" />
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="hw-skeleton h-28 rounded-xl" />
              ))}
            </div>
            <div className="hw-skeleton h-64 rounded-xl" />
          </div>
          <div className="hw-skeleton h-96 rounded-xl" />
        </div>
      ) : error && !data ? null : data ? (
        <>
          {/* ---- Active alert banner ---- */}
          {activeAlerts.length > 0 && (
            <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50/80 px-4 py-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-100 text-red-600">
                <AlertTriangleIcon className="h-4.5 w-4.5" style={{ width: 18, height: 18 }} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-red-800">
                  Active {activeAlerts[0].risk_level} heatwave alert — {activeAlerts[0].location_name ?? data.location.display_name}
                </p>
                <p className="mt-0.5 text-sm leading-snug text-red-700">{activeAlerts[0].message}</p>
                <p className="mt-1 text-[11px] text-red-400">
                  Generated {relativeTime(activeAlerts[0].generated_at)} · HeatWatch AI system alert, not an official advisory
                </p>
              </div>
              <Link to="/alerts" className="shrink-0 self-center text-xs font-bold text-red-700 underline underline-offset-2">
                Manage
              </Link>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            {/* ================= MAIN COLUMN ================= */}
            <div className="min-w-0 space-y-4 xl:col-span-2">
              {/* ---- Primary climate intelligence: risk assessment ---- */}
              <section
                aria-label="AI heatwave risk assessment"
                className={`relative overflow-hidden rounded-xl border bg-white shadow-card ${
                  hasPrediction && (p as any).risk_category === "high"
                    ? "border-red-200"
                    : hasPrediction && (p as any).risk_category === "moderate"
                      ? "border-amber-200"
                      : "border-green-200"
                }`}
              >
                <span
                  aria-hidden
                  className={`absolute inset-y-0 left-0 w-1 ${
                    hasPrediction && (p as any).risk_category === "high"
                      ? "bg-red-600"
                      : hasPrediction && (p as any).risk_category === "moderate"
                        ? "bg-amber-500"
                        : "bg-green-600"
                  }`}
                />
                {hasPrediction ? (
                  <div className="p-4 pl-5">
                    <div className="flex flex-col gap-5 md:flex-row md:items-center">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400">
                            AI-predicted heatwave level
                          </p>
                          <Pill
                            text={(p as any).data_mode === "demo" ? "DEMO MODEL OUTPUT" : "LIVE"}
                            className={
                              (p as any).data_mode === "demo"
                                ? "border-violet-200 bg-violet-50 text-violet-700"
                                : "border-emerald-200 bg-emerald-50 text-emerald-700"
                            }
                          />
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                          <RiskBadge category={(p as any).risk_category as RiskCategory} />
                          <p className="tnum text-[26px] font-semibold leading-7 tracking-tight text-slate-900">
                            {(p as any).severity_score.toFixed(0)}
                            <span className="text-sm font-medium text-slate-400">/100</span>
                          </p>
                        </div>
                        <div className="mt-3 max-w-md">
                          <RiskScale score={(p as any).severity_score} category={(p as any).risk_category as RiskCategory} />
                        </div>
                        <p className="mt-3 text-xs text-slate-500">
                          {(p as any).confidence != null ? (
                            <>
                              Weather-model confidence{" "}
                              <span className="tnum font-semibold text-slate-700">{(p as any).confidence.toFixed(0)}%</span>
                              {" · "}
                            </>
                          ) : (
                            "Rule-based method (no statistical confidence) · "
                          )}
                          assessed {formatTime((p as any).predicted_at)}
                        </p>
                      </div>
                      <dl className="grid min-w-0 grid-cols-3 gap-x-5 gap-y-2 text-xs md:border-l md:border-slate-100 md:pl-5">
                        <div className="min-w-0">
                          <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Weather model</dt>
                          <dd className="tnum mt-0.5 text-sm font-semibold text-slate-800">
                            {(p as any).weather_model_risk?.toFixed(0) ?? "—"}/100
                          </dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Sentiment adj.</dt>
                          <dd className="tnum mt-0.5 text-sm font-semibold text-slate-800">
                            +{(p as any).sentiment_adjustment ?? 0}
                          </dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Model</dt>
                          <dd
                            className="mt-0.5 truncate text-sm font-semibold text-slate-800"
                            title={(p as any).model_version}
                          >
                            {(p as any).model_version}
                          </dd>
                        </div>
                      </dl>
                    </div>
                    <p className="mt-3 border-t border-slate-100 pt-2.5 text-[11px] leading-relaxed text-slate-400">
                      Severity fuses the weather-based model with a bounded, upward-only public-distress adjustment
                      (max +12). Methodology:{" "}
                      <span className="break-all">{(p as any).methodology}</span>
                    </p>
                  </div>
                ) : (
                  <div className="p-5">
                    <EmptyState
                      title="No prediction yet"
                      hint="Run the monitoring pipeline to produce the first severity assessment for this location."
                      action={<Button small onClick={refreshNow}>Run pipeline</Button>}
                    />
                  </div>
                )}
              </section>

              {/* ---- Weather metrics ---- */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Current conditions</h3>
                  {w?.available !== false && w && (
                    <p className="tnum text-[11px] text-slate-400">
                      <ClockIcon className="mr-1 inline h-3 w-3 -translate-y-px" />
                      Observed {formatTime(w.observed_at)} ({relativeTime(w.observed_at)}) · {w.provider}
                    </p>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <MetricTile
                    label="Temperature"
                    value={w?.available === false ? "—" : `${w?.temperature_c.toFixed(1) ?? "—"}°`}
                    sub={w?.feels_like_c != null ? `Feels like ${w.feels_like_c.toFixed(1)}°C` : undefined}
                    icon={<TempIcon className="h-4 w-4" />}
                  />
                  <MetricTile
                    label="Humidity"
                    value={w?.available === false ? "—" : `${w?.humidity_pct.toFixed(0) ?? "—"}%`}
                    sub={w?.humidity_pct == null ? undefined : w.humidity_pct > 70 ? "Humid" : w.humidity_pct > 40 ? "Moderate" : "Dry"}
                    icon={<DropIcon className="h-4 w-4" />}
                  />
                  <MetricTile
                    label="Heat index"
                    value={hiAvailable ? `${w!.heat_index_c!.toFixed(1)}°` : "N/A"}
                    sub={hiAvailable ? "NWS Rothfusz method" : "Not applicable for this observation"}
                    icon={<HeatIcon className="h-4 w-4" />}
                    tone={!hiAvailable ? "neutral" : (w!.heat_index_c!) >= 41 ? "high" : (w!.heat_index_c!) >= 32 ? "moderate" : "low"}
                  />
                  <MetricTile
                    label="Wind"
                    value={w?.available === false ? "—" : `${w?.wind_speed_kph.toFixed(0) ?? "—"} km/h`}
                    sub={w?.condition_text}
                    icon={<WindIcon className="h-4 w-4" />}
                  />
                </div>
                {w?.available !== false && w && !hiAvailable && (
                  <p className="mt-1.5 text-[11px] text-slate-400">
                    Heat index is only calculated inside the NWS applicability envelope; air temperature is used as the
                    thermal-stress proxy.
                  </p>
                )}
              </div>

              {/* ---- Charts ---- */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <Card
                  title="Temperature & heat index"
                  subtitle="Stored observations · last 7 days · °C"
                  bodyClassName="p-3"
                >
                  {wSeries.length >= 2 ? (
                    <ResponsiveContainer width="100%" height={190}>
                      <LineChart data={wSeries} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis
                          dataKey="observed_at"
                          tickFormatter={tickFormatter}
                          tick={{ fontSize: 10 }}
                          tickLine={false}
                          axisLine={{ stroke: "#e2e8f0" }}
                          minTickGap={48}
                          interval="preserveStartEnd"
                        />
                        <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={44} unit="°" />
                        <Tooltip
                          content={<ChartTooltip valueFormatter={(v: number) => `${Number(v).toFixed(1)} °C`} />}
                        />
                        <Line
                          type="monotone"
                          dataKey="temperature_c"
                          name="Temperature"
                          stroke={CHART_COLORS.temperature}
                          strokeWidth={1.8}
                          dot={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="heat_index_c"
                          name="Heat index"
                          stroke={CHART_COLORS.heatIndex}
                          strokeWidth={1.6}
                          dot={false}
                          connectNulls={false}
                          strokeDasharray="4 3"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <EmptyState compact title="Not enough observations yet" hint="Keep collecting data to build the trend." />
                  )}
                </Card>

                <Card
                  title="Predicted severity"
                  subtitle="Fused score 0–100 · thresholds 40 / 70"
                  bodyClassName="p-3"
                >
                  {severitySeries.length >= 2 ? (
                    <ResponsiveContainer width="100%" height={190}>
                      <LineChart data={severitySeries} margin={{ top: 6, right: 10, left: -22, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis
                          dataKey="predicted_at"
                          tickFormatter={severityFormatter}
                          tick={{ fontSize: 10 }}
                          tickLine={false}
                          axisLine={{ stroke: "#e2e8f0" }}
                          minTickGap={48}
                          interval="preserveStartEnd"
                        />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={40} />
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
                    <EmptyState compact title="Not enough predictions yet" />
                  )}
                </Card>

                <Card title="Sentiment distribution" subtitle="Latest aggregated window" bodyClassName="p-3">
                  {sentimentPie.length > 0 ? (
                    <div className="flex items-center gap-4">
                      <ResponsiveContainer width="50%" height={160}>
                        <PieChart>
                          <Pie
                            data={sentimentPie}
                            dataKey="value"
                            nameKey="name"
                            innerRadius={44}
                            outerRadius={70}
                            paddingAngle={3}
                            stroke="none"
                          >
                            {sentimentPie.map((d) => (
                              <Cell key={d.name} fill={d.color} />
                            ))}
                          </Pie>
                          <Tooltip content={<ChartTooltip valueFormatter={(v: number) => `${v} posts`} />} />
                        </PieChart>
                      </ResponsiveContainer>
                      <ul className="min-w-0 flex-1 space-y-1.5 text-xs">
                        {sentimentPie.map((d) => {
                          const total = sentimentPie.reduce((a, b) => a + b.value, 0);
                          return (
                            <li key={d.name} className="flex items-center justify-between gap-2">
                              <span className="flex items-center gap-1.5 text-slate-600">
                                <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                                {d.name}
                              </span>
                              <span className="tnum font-semibold text-slate-800">
                                {d.value} <span className="font-normal text-slate-400">({Math.round((d.value / total) * 100)}%)</span>
                              </span>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : (
                    <EmptyState compact title="No sentiment data yet" />
                  )}
                </Card>

                <Card title="Alert frequency" subtitle="Alerts per day · last 7 days" bodyClassName="p-3">
                  {data.series.alert_frequency.length > 0 ? (
                    <ResponsiveContainer width="100%" height={160}>
                      <BarChart data={data.series.alert_frequency} margin={{ top: 6, right: 10, left: -28, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis
                          dataKey="day"
                          tickFormatter={(d: string) => d.slice(5)}
                          tick={{ fontSize: 10 }}
                          tickLine={false}
                          axisLine={{ stroke: "#e2e8f0" }}
                        />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={30} />
                        <Tooltip content={<ChartTooltip valueFormatter={(v: number) => `${v} alert${v === 1 ? "" : "s"}`} />} />
                        <Bar dataKey="count" name="Alerts" fill={CHART_COLORS.alert} radius={[4, 4, 0, 0]} maxBarSize={28} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <EmptyState
                      compact
                      title="No alerts in the last 7 days"
                      hint="Risk has stayed below the configured thresholds."
                    />
                  )}
                </Card>
              </div>
            </div>

            {/* ================= SIDE PANEL ================= */}
            <div className="min-w-0 space-y-4">
              {/* Public sentiment panel */}
              <Card
                title="Public sentiment"
                subtitle="VADER · English posts · trailing 24h"
                action={
                  <Link to="/sentiment" className="text-xs font-semibold text-brand hover:underline">
                    Analyse
                  </Link>
                }
              >
                {s?.available && s.post_count > 0 ? (
                  <div>
                    <div className="flex items-end gap-2">
                      <p className="tnum text-3xl font-semibold tracking-tight text-slate-900">
                        {s.avg_score != null ? s.avg_score.toFixed(2) : "—"}
                      </p>
                      <p className="pb-1 text-xs text-slate-400">avg compound score</p>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                      {[
                        { label: "Positive", v: s.positive_count, cls: "text-green-700" },
                        { label: "Neutral", v: s.neutral_count, cls: "text-slate-600" },
                        { label: "Negative", v: s.negative_count, cls: "text-red-600" },
                      ].map((m) => (
                        <div key={m.label} className="rounded-lg bg-slate-50 py-1.5">
                          <p className={`tnum text-sm font-bold ${m.cls}`}>{m.v}</p>
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{m.label}</p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center justify-between rounded-lg border border-orange-200 bg-orange-50/70 px-3 py-2">
                      <span className="text-xs font-semibold text-orange-800">Heat-related distress signals</span>
                      <span className="tnum text-sm font-bold text-orange-700">
                        {s.distress_count}
                        <span className="text-[10px] font-medium text-orange-500"> / {s.heat_related_count} heat posts</span>
                      </span>
                    </div>
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                      {s.post_count} posts analysed · {s.data_mode === "demo" ? "demonstration feed" : "live feed"} ·
                      distress counts only heat-relevant posts with impact vocabulary; general sentiment is not a
                      standalone severity measure.
                    </p>
                  </div>
                ) : (
                  <EmptyState compact title="No sentiment data" hint="Collect social data for this location." />
                )}
              </Card>

              {/* Recent posts */}
              <Card
                title={
                  <span className="inline-flex items-center gap-1.5">
                    <ChatIcon className="h-3.5 w-3.5 text-slate-400" /> Recent public posts
                  </span>
                }
                subtitle="Distress & heat-related first"
                bodyClassName="p-3"
              >
                {posts.length ? (
                  <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
                    {posts.map((post) => (
                      <li key={post.id} className="rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2.5">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="font-semibold text-slate-600">{post.author_handle ?? post.source_platform}</span>
                          <span className="text-slate-400">{relativeTime(post.published_at)}</span>
                        </div>
                        <p className="mt-1 text-xs leading-snug text-slate-700">{post.text}</p>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {post.sentiment && (
                            <StatusPill
                              text={postSentimentPill(post.sentiment).text}
                              className={postSentimentPill(post.sentiment).className}
                            />
                          )}
                          {post.sentiment?.is_heat_related && (
                            <StatusPill text="HEAT-RELATED" className="border-orange-200 bg-orange-50 text-orange-700" />
                          )}
                          {post.sentiment?.distress_flag && (
                            <StatusPill text="DISTRESS" className="border-red-200 bg-red-100 text-red-800" />
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState compact title="No posts collected yet" hint="Run the data collection pipeline." />
                )}
              </Card>

              {/* Advisory */}
              <Card title="Government advisory">
                {data.advisory.available ? (
                  <div>
                    <p className="text-sm font-semibold leading-snug text-slate-800">{data.advisory.title}</p>
                    <p className="mt-1 text-xs leading-relaxed text-slate-600">{data.advisory.body}</p>
                    <p className="mt-2 text-[11px] text-slate-400">
                      Source: {data.advisory.source_name}
                      {data.advisory.published_at && ` · ${formatTime(data.advisory.published_at)}`}
                    </p>
                    {data.advisory.is_demo && (
                      <div className="mt-2">
                        <StatusPill
                          text="DEMONSTRATION CONTENT — NOT AN OFFICIAL ADVISORY"
                          className="border-amber-200 bg-amber-50 text-amber-800"
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  <EmptyState
                    compact
                    title="No verified advisory source configured"
                    hint={data.advisory.message}
                  />
                )}
              </Card>

              {/* Emergency contacts */}
              <Card
                title={
                  <span className="inline-flex items-center gap-1.5">
                    <PhoneIcon className="h-3.5 w-3.5 text-slate-400" /> Emergency contacts
                  </span>
                }
                bodyClassName="px-2 py-1"
              >
                <ul className="divide-y divide-slate-100">
                  {data.emergency_contacts.map((c) => (
                    <li key={c.id} className="flex items-center justify-between px-2 py-2 text-sm">
                      <span className="min-w-0 truncate text-slate-600">{c.name}</span>
                      <span className="tnum ml-2 font-mono text-[13px] font-semibold text-slate-900">{c.phone}</span>
                    </li>
                  ))}
                </ul>
                <p className="px-2 pb-2 pt-1 text-[10.5px] text-slate-400">
                  Reference only — administrator-maintained national helplines (India).
                </p>
              </Card>

              {/* Compact contextual actions */}
              <Card title="Reports">
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="secondary"
                    small
                    onClick={() => generateReport("pdf")}
                    disabled={busyAction === "pdf"}
                    icon={<DownloadIcon className="h-3.5 w-3.5" />}
                  >
                    PDF · 7 days
                  </Button>
                  <Button
                    variant="secondary"
                    small
                    onClick={() => generateReport("csv")}
                    disabled={busyAction === "csv"}
                    icon={<DownloadIcon className="h-3.5 w-3.5" />}
                  >
                    CSV · 7 days
                  </Button>
                </div>
                <Link
                  to="/reports"
                  className="mt-2.5 flex items-center justify-center rounded-lg border border-slate-200 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Custom range & report history
                </Link>
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
