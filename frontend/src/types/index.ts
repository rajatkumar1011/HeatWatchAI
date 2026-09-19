// Shared API types for HeatWatch AI (mirrors backend schemas).

export type RiskCategory = "low" | "moderate" | "high";
export type DataMode = "live" | "demo" | "mixed";
export type Freshness = "live" | "cached" | "demo";

export interface User {
  id: number;
  username: string;
  email: string;
  role: "admin" | "officer" | "authority" | "researcher";
  role_label: string;
  is_active: boolean;
  is_demo: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface Location {
  id: number;
  name: string;
  state: string;
  display_name: string;
  country: string;
  latitude: number;
  longitude: number;
  is_monitored: boolean;
  timezone: string;
}

export interface WeatherObservation {
  id?: number;
  location_id?: number;
  temperature_c: number;
  feels_like_c: number | null;
  humidity_pct: number;
  heat_index_c: number | null;
  wind_speed_kph: number;
  wind_deg: number | null;
  pressure_hpa: number | null;
  condition_code: number | null;
  condition_text: string;
  observed_at: string;
  ingested_at?: string;
  provider: string;
  data_mode: DataMode;
  freshness?: Freshness;
}

export interface Prediction {
  id: number;
  location_id: number;
  weather_observation_id: number | null;
  sentiment_aggregate_id: number | null;
  predicted_at: string;
  risk_category: RiskCategory;
  severity_score: number;
  weather_model_risk: number | null;
  confidence: number | null;
  methodology: string;
  model_version: string;
  sentiment_adjustment: number | null;
  contributing_factors: string | null;
  inputs: string | null;
  data_mode: DataMode;
  available?: boolean;
}

export interface SentimentSummary {
  available?: boolean;
  post_count: number;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  avg_score: number | null;
  heat_related_count: number;
  distress_count: number;
  window_start?: string;
  window_end?: string;
  data_mode?: DataMode;
}

export interface PostSentiment {
  label: "positive" | "neutral" | "negative";
  score: number;
  is_heat_related: boolean;
  distress_flag: boolean;
  model_name: string;
  model_version: string;
}

export interface SocialPost {
  id: number;
  source_platform: string;
  text: string;
  author_handle: string | null;
  published_at: string;
  location_id: number | null;
  raw_location_label: string | null;
  data_mode: DataMode;
  analysis_status: string;
  sentiment?: PostSentiment | null;
}

export interface Alert {
  id: number;
  prediction_id: number | null;
  location_id: number;
  location_name?: string;
  risk_level: RiskCategory;
  severity_score: number;
  message: string;
  triggered_by: string;
  status: "active" | "acknowledged" | "resolved";
  acknowledged_at: string | null;
  generated_at: string;
  resolved_at: string | null;
  data_mode: DataMode;
}

export interface Advisory {
  id?: number;
  available?: boolean;
  title: string;
  body: string;
  source_name: string;
  source_url: string | null;
  published_at: string | null;
  is_demo: boolean;
  message?: string;
}

export interface EmergencyContact {
  id: number;
  name: string;
  phone: string;
  category: string;
  notes: string | null;
}

export interface ReportRecord {
  id: number;
  user_id: number | null;
  username: string | null;
  location_id: number;
  location_name: string | null;
  start_date: string;
  end_date: string;
  format: "pdf" | "csv";
  status: string;
  generated_at: string;
  data_mode: DataMode;
}

export interface DashboardPayload {
  location: Location;
  generated_at: string;
  weather: WeatherObservation & { available?: boolean; message?: string };
  prediction: Prediction | { available: false };
  sentiment: SentimentSummary;
  posts: SocialPost[];
  alerts: Alert[];
  advisory: Advisory;
  emergency_contacts: EmergencyContact[];
  series: {
    weather: WeatherObservation[];
    predictions: Prediction[];
    sentiment_aggregates: SentimentSummary[];
    alert_frequency: { day: string; count: number }[];
  };
}

export interface SystemLog {
  id: number;
  level: string;
  category: string;
  message: string;
  details: string | null;
  created_at: string;
}

export interface AdminUser extends User {}
