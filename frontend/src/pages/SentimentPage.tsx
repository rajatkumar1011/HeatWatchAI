import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "../api/client";
import type { Location, SentimentSummary, SocialPost } from "../types";
import { Button, Card, EmptyState, ErrorState, MetricTile, PageHeader, Pill, SegmentedControl, Select, Skeleton, useToast } from "../components/ui";
import { StatusPill } from "../components/Risk";
import { ChatIcon, RefreshIcon, SearchIcon } from "../components/icons";
import { relativeTime } from "../utils/format";

type Filter = "all" | "positive" | "neutral" | "negative";

export function SentimentPage() {
  const toast = useToast();
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<number | null>(null);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [summary, setSummary] = useState<SentimentSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [heatOnly, setHeatOnly] = useState(false);
  const [busy, setBusy] = useState(false);

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
      const params = new URLSearchParams({ location_id: String(locationId), per_page: "60" });
      if (filter !== "all") params.set("sentiment", filter);
      if (heatOnly) params.set("heat_related", "1");
      const [p, s] = await Promise.all([
        api.get(`/social/posts?${params.toString()}`),
        api.get(`/social/summary?location_id=${locationId}`),
      ]);
      // display-level dedup of identical text (repeated demo templates)
      const seen = new Set<string>();
      const unique = (p.data.data as SocialPost[]).filter((post) => {
        const key = post.text.trim().toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      setPosts(unique);
      setSummary(s.data.data);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [locationId, filter, heatOnly]);

  useEffect(() => {
    load();
  }, [load]);

  const collect = async () => {
    setBusy(true);
    try {
      await api.post("/social/collect", { location_id: locationId });
      await load();
      toast("success", "Collection and sentiment analysis completed.");
    } catch (err) {
      toast("error", errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const distressShare = useMemo(() => {
    if (!summary?.available || !summary.post_count) return null;
    return Math.round((summary.distress_count / summary.post_count) * 100);
  }, [summary]);

  return (
    <div>
      <PageHeader
        title="Public Sentiment"
        description="NLP analysis of public posts (VADER, English). General sentiment is reported separately from heat-related distress — a negative post is not necessarily heat distress."
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
          variant="secondary"
          onClick={collect}
          disabled={busy}
          icon={<RefreshIcon className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />}
        >
          Collect &amp; analyse
        </Button>
      </PageHeader>

      {/* Summary metrics */}
      {summary?.available ? (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
          <MetricTile label="Posts analysed" value={summary.post_count} icon={<ChatIcon className="h-4 w-4" />} />
          <MetricTile label="Positive" value={summary.positive_count} tone="low" />
          <MetricTile label="Neutral" value={summary.neutral_count} />
          <MetricTile label="Negative" value={summary.negative_count} tone="high" />
          <MetricTile
            label="Distress signals"
            value={summary.distress_count}
            sub={distressShare != null ? `${distressShare}% of analysed posts` : undefined}
            tone="moderate"
          />
        </div>
      ) : null}

      {/* Filter bar */}
      <div className="mb-3 flex flex-wrap items-center gap-2.5">
        <SegmentedControl
          ariaLabel="Sentiment filter"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All" },
            { value: "positive", label: "Positive" },
            { value: "neutral", label: "Neutral" },
            { value: "negative", label: "Negative" },
          ]}
        />
        <button
          onClick={() => setHeatOnly((v) => !v)}
          aria-pressed={heatOnly}
          className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
            heatOnly
              ? "border-orange-300 bg-orange-50 text-orange-800"
              : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          }`}
        >
          <SearchIcon className="h-3.5 w-3.5" />
          Heat-related only
        </button>
        {heatOnly && (
          <span className="text-[11px] text-slate-400">
            Showing posts whose text matches the heat-vocabulary configuration.
          </span>
        )}
      </div>

      {/* Post feed */}
      <Card title="Post feed" subtitle="Newest first · duplicates hidden" bodyClassName="p-3">
        {loading ? (
          <div className="space-y-2 p-1">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-lg" />
            ))}
          </div>
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : posts.length === 0 ? (
          <EmptyState
            title="No posts match the current filters"
            hint="Try a different sentiment filter, or collect fresh data for this location."
            action={
              <Button small variant="secondary" onClick={collect} disabled={busy}>
                Collect now
              </Button>
            }
          />
        ) : (
          <ul className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
            {posts.map((post) => (
              <li
                key={post.id}
                className="rounded-lg border border-slate-100 bg-white px-3.5 py-3 transition-colors hover:border-slate-200"
              >
                <div className="flex items-center justify-between gap-2 text-[11px]">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-slate-100 text-[9px] font-bold text-slate-500">
                      {(post.author_handle ?? post.source_platform ?? "?").replace("@", "").slice(0, 2).toUpperCase()}
                    </span>
                    <span className="truncate font-semibold text-slate-600">
                      {post.author_handle ?? post.source_platform}
                    </span>
                  </span>
                  <span className="shrink-0 text-slate-400">{relativeTime(post.published_at)}</span>
                </div>
                <p className="mt-1.5 text-sm leading-snug text-slate-700">{post.text}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {post.sentiment ? (
                    <>
                      <StatusPill
                        text={
                          post.sentiment.label === "negative"
                            ? `NEGATIVE ${post.sentiment.score.toFixed(2)}`
                            : post.sentiment.label === "positive"
                              ? `POSITIVE +${post.sentiment.score.toFixed(2)}`
                              : "NEUTRAL"
                        }
                        className={
                          post.sentiment.label === "negative"
                            ? "border-red-200 bg-red-50 text-red-700"
                            : post.sentiment.label === "positive"
                              ? "border-green-200 bg-green-50 text-green-700"
                              : "border-slate-200 bg-slate-50 text-slate-600"
                        }
                      />
                      {post.sentiment.is_heat_related && (
                        <StatusPill text="HEAT-RELATED" className="border-orange-200 bg-orange-50 text-orange-700" />
                      )}
                      {post.sentiment.distress_flag && (
                        <StatusPill text="DISTRESS" className="border-red-200 bg-red-100 text-red-800" />
                      )}
                      <span className="text-[10px] text-slate-400">
                        via {post.sentiment.model_name} v{post.sentiment.model_version}
                      </span>
                    </>
                  ) : (
                    <StatusPill text="NOT ANALYSED" className="border-slate-200 bg-slate-50 text-slate-500" />
                  )}
                  {!post.location_id && <Pill text="NO LOCATION DATA" className="border-slate-200 bg-slate-50 text-slate-400" />}
                  {post.data_mode === "demo" && <Pill text="DEMO" className="border-violet-200 bg-violet-50 text-violet-700" />}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
