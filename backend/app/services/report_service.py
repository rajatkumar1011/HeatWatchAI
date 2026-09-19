"""Historical report generation (FR-08): PDF (ReportLab) and CSV exports.

Reports are generated strictly from the database records matching the
requested location and date range. Demonstration data rows carry their
provenance into the report so DEMO data is never presented as LIVE.

The PDF follows the HeatWatch AI design system (deep-crimson brand
#BD1426, navy #111827 headings, cool-neutral surfaces, semantic risk
colours) so exports visually match the application.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.extensions import db
from app.models import Alert, Location, Prediction, ReportRecord, SentimentAggregate, WeatherObservation
from app.utils.heat import compute_heat_index_c
from app.utils.responses import log_event
from app.utils.timeutils import as_utc, utcnow

REPORT_BRAND = "HeatWatch AI"
REPORT_TAGLINE = "AI-Based Climate Intelligence System for Heatwave Monitoring, Prediction, and Early Warning"

# Design tokens (mirror frontend/src/styles/index.css)
BRAND = "#BD1426"
NAVY = "#111827"
INK = "#1E293B"
SLATE = "#64748B"
MUTED = "#94A3B8"
BORDER = "#E2E8F0"
SURFACE = "#F7F9FC"
RISK_LOW = "#16A34A"
RISK_MODERATE = "#D97706"
RISK_HIGH = "#DC2626"
DEMO_VIOLET = "#7C3AED"
LIVE_GREEN = "#059669"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _mode_labels(rows) -> str:
    modes = sorted({r.data_mode for r in rows})
    return ", ".join(m.upper() for m in modes) if modes else "N/A"


class ReportService:
    def __init__(self, config):
        self.config = config

    # ------------------------------------------------------------- queries
    def collect_data(self, location: Location, start: date, end: date) -> dict:
        start_dt = as_utc(datetime(start.year, start.month, start.day)) 
        end_dt = as_utc(datetime(end.year, end.month, end.day) + timedelta(days=1)) - timedelta(seconds=1)
        if end_dt < start_dt:
            raise ValueError("End date must be on or after the start date.")

        weather = list(db.session.execute(
            select(WeatherObservation)
            .where(WeatherObservation.location_id == location.id,
                   WeatherObservation.observed_at >= start_dt,
                   WeatherObservation.observed_at <= end_dt)
            .order_by(WeatherObservation.observed_at.asc())
        ).scalars())
        predictions = list(db.session.execute(
            select(Prediction)
            .where(Prediction.location_id == location.id,
                   Prediction.predicted_at >= start_dt,
                   Prediction.predicted_at <= end_dt)
            .order_by(Prediction.predicted_at.asc())
        ).scalars())
        aggregates = list(db.session.execute(
            select(SentimentAggregate)
            .where(SentimentAggregate.location_id == location.id,
                   SentimentAggregate.window_end >= start_dt,
                   SentimentAggregate.window_start <= end_dt)
            .order_by(SentimentAggregate.window_start.asc())
        ).scalars())
        alerts = list(db.session.execute(
            select(Alert)
            .where(Alert.location_id == location.id,
                   Alert.generated_at >= start_dt,
                   Alert.generated_at <= end_dt)
            .order_by(Alert.generated_at.asc())
        ).scalars())
        return {
            "start_dt": start_dt, "end_dt": end_dt,
            "weather": weather, "predictions": predictions,
            "aggregates": aggregates, "alerts": alerts,
        }

    def summarize(self, location: Location, data: dict) -> dict:
        weather = data["weather"]
        temps = [w.temperature_c for w in weather]
        humidity = [w.humidity_pct for w in weather]
        his = [w.heat_index_c for w in weather if w.heat_index_c is not None]
        winds = [w.wind_speed_kph for w in weather]
        predictions = data["predictions"]
        aggregates = data["aggregates"]
        alerts = data["alerts"]

        risk_counts = {"low": 0, "moderate": 0, "high": 0}
        for p in predictions:
            if p.risk_category in risk_counts:
                risk_counts[p.risk_category] += 1

        posts = sum(a.post_count for a in aggregates)
        heat_related = sum(a.heat_related_count for a in aggregates)
        distress = sum(a.distress_count for a in aggregates)
        positive = sum(a.positive_count for a in aggregates)
        neutral = sum(a.neutral_count for a in aggregates)
        negative = sum(a.negative_count for a in aggregates)

        return {
            "weather": {
                "observations": len(weather),
                "temp_avg": _mean(temps), "temp_max": max(temps) if temps else None,
                "temp_min": min(temps) if temps else None,
                "humidity_avg": _mean(humidity),
                "heat_index_avg": _mean(his), "heat_index_max": max(his) if his else None,
                "heat_index_available_obs": len(his),
                "wind_avg": _mean(winds),
                "modes": _mode_labels(weather),
            },
            "risk": {
                "predictions": len(predictions),
                "counts": risk_counts,
                "score_avg": _mean([p.severity_score for p in predictions]),
                "score_max": max((p.severity_score for p in predictions), default=None),
                "modes": _mode_labels(predictions),
            },
            "sentiment": {
                "aggregates": len(aggregates),
                "posts": posts,
                "positive": positive, "neutral": neutral, "negative": negative,
                "heat_related": heat_related, "distress": distress,
                "avg_score": _mean([a.avg_score for a in aggregates if a.avg_score is not None]),
                "modes": _mode_labels(aggregates),
            },
            "alerts": {"count": len(alerts), "high": sum(1 for a in alerts if a.risk_level == "high"),
                       "moderate": sum(1 for a in alerts if a.risk_level == "moderate"),
                       "modes": _mode_labels(alerts)},
        }

    # ------------------------------------------------------------ generate
    def generate(self, user, location: Location, start: date, end: date, fmt: str) -> ReportRecord:
        fmt = fmt.lower()
        if fmt not in ("pdf", "csv"):
            raise ValueError("Report format must be 'pdf' or 'csv'.")
        if start > end:
            raise ValueError("Start date must be on or before the end date.")
        if start > utcnow().date():
            raise ValueError("Start date cannot be in the future.")
        if (end - start).days > 366:
            raise ValueError("Reporting period cannot exceed 366 days.")

        data = self.collect_data(location, start, end)
        summary = self.summarize(location, data)
        if summary["weather"]["observations"] == 0 and summary["risk"]["predictions"] == 0:
            raise ValueError("No records found for the selected location and date range.")

        out_dir = Path(self.config["REPORT_OUTPUT_DIR"])
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = location.display_name.replace(",", "").replace(" ", "_")
        filename = f"heatwatch_{fmt}_{safe_name}_{start.isoformat()}_{end.isoformat()}_{stamp}.{fmt}"
        file_path = out_dir / filename

        if fmt == "pdf":
            self._write_pdf(file_path, location, start, end, summary, data)
        else:
            self._write_csv(file_path, location, data)

        record = ReportRecord(
            user_id=getattr(user, "id", None),
            location_id=location.id,
            start_date=start, end_date=end,
            format=fmt, file_path=str(file_path), status="completed",
            params_json=json.dumps({"location": location.display_name, "start": start.isoformat(),
                                    "end": end.isoformat(), "format": fmt}),
            data_mode="demo" if "DEMO" in _mode_labels(data["weather"]) and "LIVE" not in _mode_labels(data["weather"]) else ("mixed" if "DEMO" in _mode_labels(data["weather"]) else "live"),
        )
        db.session.add(record)
        db.session.commit()
        log_event("report", f"{fmt.upper()} report generated for {location.display_name}",
                  details={"report_id": record.id, "user_id": getattr(user, 'id', None)})
        return record

    # ----------------------------------------------------------------- PDF
    def _write_pdf(self, path: Path, location: Location, start: date, end: date,
                   summary: dict, data: dict) -> None:
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.shapes import Drawing
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        def C(hex_: str) -> colors.Color:
            return colors.HexColor(hex_)

        styles = getSampleStyleSheet()
        brand = ParagraphStyle("Brand", parent=styles["Title"], textColor=C(BRAND),
                               fontSize=20, leading=24, spaceAfter=0)
        tagline = ParagraphStyle("Tagline", parent=styles["Normal"], fontSize=8.5,
                                 leading=11, textColor=C(SLATE))
        doc_title = ParagraphStyle("DocTitle", parent=styles["Heading1"], textColor=C(NAVY),
                                   fontSize=15, leading=19, spaceBefore=2, spaceAfter=0)
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=C(NAVY),
                            fontSize=11.5, leading=15, spaceBefore=4, spaceAfter=3)
        body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8.5, leading=12, textColor=C(INK))
        small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=7.6, leading=10.5, textColor=C(SLATE))
        meta_label = ParagraphStyle("MetaLabel", parent=styles["Normal"], fontSize=8,
                                    textColor=C(MUTED), fontName="Helvetica-Bold")
        meta_value = ParagraphStyle("MetaValue", parent=styles["Normal"], fontSize=8.5, textColor=C(INK))

        generated_at = utcnow()
        doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=16 * mm, bottomMargin=18 * mm,
                                leftMargin=16 * mm, rightMargin=16 * mm,
                                title=f"{REPORT_BRAND} Historical Report",
                                author=REPORT_BRAND)

        def _footer(canvas, _doc):
            canvas.saveState()
            canvas.setStrokeColor(C(BORDER))
            canvas.setLineWidth(0.5)
            canvas.line(16 * mm, 13 * mm, A4[0] - 16 * mm, 13 * mm)
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(C(SLATE))
            canvas.drawString(16 * mm, 9 * mm, f"{REPORT_BRAND} — {REPORT_TAGLINE}")
            canvas.drawRightString(A4[0] - 16 * mm, 9 * mm,
                                   f"Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')} · Page {canvas.getPageNumber()}")
            canvas.restoreState()

        story = []

        # ---- Masthead -----------------------------------------------------
        story.append(Paragraph(REPORT_BRAND, brand))
        story.append(Paragraph(REPORT_TAGLINE, tagline))
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=1.6, color=C(BRAND), spaceAfter=8))
        story.append(Paragraph("Historical Data Report", doc_title))
        story.append(Spacer(1, 6))

        meta_rows = [
            [Paragraph("LOCATION", meta_label), Paragraph("REPORTING PERIOD", meta_label),
             Paragraph("GENERATED", meta_label)],
            [Paragraph(location.display_name, meta_value),
             Paragraph(f"{start.isoformat()} to {end.isoformat()}", meta_value),
             Paragraph(generated_at.strftime("%d %b %Y, %H:%M UTC") +
                       f" · display tz {self.config['DISPLAY_TIMEZONE']}", meta_value)],
            [Paragraph("COORDINATES", meta_label), Paragraph("DATA PROVENANCE", meta_label),
             Paragraph("UNITS", meta_label)],
            [Paragraph(f"{location.latitude:.4f}, {location.longitude:.4f}", meta_value),
             Paragraph(_mode_labels(data["weather"] + data["predictions"] + data["alerts"]), meta_value),
             Paragraph("°C · km/h · hPa", meta_value)],
        ]
        meta_table = Table(meta_rows, colWidths=[58 * mm, 58 * mm, 58 * mm])
        meta_table.setStyle(TableStyle([
            ("SPAN", (0, 1), (0, 1)),
            ("BACKGROUND", (0, 0), (-1, -1), C(SURFACE)),
            ("BOX", (0, 0), (-1, -1), 0.6, C(BORDER)),
            ("LINEBELOW", (0, 1), (-1, 1), 0.4, C(BORDER)),
            ("LINEBELOW", (0, 2), (-1, 2), 0.0, C(SURFACE)),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
            ("TOPPADDING", (0, 2), (-1, 2), 5),
            ("BOTTOMPADDING", (0, 2), (-1, 2), 1),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
            ("BOTTOMPADDING", (0, 3), (-1, 3), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # ---- 1. Weather statistics ----------------------------------------
        w = summary["weather"]
        story.append(Paragraph("1 · Weather Statistics", h2))
        story.append(HRFlowable(width="100%", thickness=0.7, color=C(BORDER), spaceAfter=5))
        story.append(Table([
            ["Metric", "Value", "Metric", "Value"],
            ["Observations stored", str(w["observations"]), "Avg temperature", f"{w['temp_avg']} °C" if w["temp_avg"] is not None else "n/a"],
            ["Max temperature", f"{w['temp_max']} °C" if w["temp_max"] is not None else "n/a", "Min temperature", f"{w['temp_min']} °C" if w["temp_min"] is not None else "n/a"],
            ["Avg humidity", f"{w['humidity_avg']} %" if w["humidity_avg"] is not None else "n/a", "Avg wind speed", f"{w['wind_avg']} km/h" if w["wind_avg"] is not None else "n/a"],
            ["Heat index (avg)", f"{w['heat_index_avg']} °C" if w["heat_index_avg"] is not None else "not available", "Heat index (max)", f"{w['heat_index_max']} °C" if w["heat_index_max"] is not None else "not available"],
        ], colWidths=[42 * mm, 40 * mm, 42 * mm, 50 * mm], style=self._table_style()))
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            f"Heat index is reported only where the NWS Rothfusz calculation is applicable "
            f"({w['heat_index_available_obs']} of {w['observations']} observations); otherwise air temperature is "
            f"used as the thermal-stress proxy and noted as unavailable.", small))

        # Temperature trend chart from actual records
        weather = data["weather"]
        if len(weather) >= 2:
            temps = [wt.temperature_c for wt in weather][:200]
            his = [wt.heat_index_c for wt in weather][:200]
            drawing = Drawing(460, 130)
            chart = HorizontalLineChart()
            chart.x, chart.y, chart.width, chart.height = 28, 16, 420, 102
            chart.data = [temps, [h if h is not None else temps[i] for i, h in enumerate(his)]]
            chart.valueAxis.valueMin = min(min(temps), min((h for h in his if h is not None), default=min(temps))) - 1
            chart.valueAxis.valueMax = max(max(temps), max((h for h in his if h is not None), default=max(temps))) + 1
            chart.valueAxis.strokeColor = C(BORDER)
            chart.valueAxis.labels.fontSize = 6
            chart.valueAxis.labels.fillColor = C(SLATE)
            chart.categoryAxis.labels.fontSize = 6
            chart.categoryAxis.labels.fillColor = C(SLATE)
            chart.categoryAxis.strokeColor = C(BORDER)
            chart.lines[0].strokeColor = C(BRAND)
            chart.lines[0].strokeWidth = 1.3
            chart.lines[1].strokeColor = C("#F97316")
            chart.lines[1].strokeWidth = 1.1
            chart.lines[1].strokeDashArray = [3, 2]
            drawing.add(chart)
            story.append(Spacer(1, 5))
            story.append(Paragraph(
                "Temperature trend (crimson) and heat index (dashed orange) — stored observations", small))
            story.append(drawing)

        # ---- 2. Risk analysis ----------------------------------------------
        story.append(Paragraph("2 · Heatwave Risk Analysis", h2))
        story.append(HRFlowable(width="100%", thickness=0.7, color=C(BORDER), spaceAfter=5))
        r = summary["risk"]
        risk_rows = [
            ["Predictions", str(r["predictions"])],
            ["Low risk", str(r["counts"]["low"])],
            ["Moderate risk", str(r["counts"]["moderate"])],
            ["High risk", str(r["counts"]["high"])],
            ["Average severity", f"{r['score_avg']} / 100" if r["score_avg"] is not None else "n/a"],
            ["Peak severity", f"{r['score_max']} / 100" if r["score_max"] is not None else "n/a"],
        ]
        risk_label_style = ParagraphStyle("RiskL", parent=body, textColor=C(INK))
        risk_val_style = ParagraphStyle("RiskV", parent=body, fontName="Helvetica-Bold")

        def _kv_coloured(rows, value_colour):
            """Build two-column Paragraph rows with colour-coded values."""
            out = []
            for label, value in rows:
                colour = value_colour.get(label, INK)
                out.append([
                    Paragraph(label, risk_label_style),
                    Paragraph(value, ParagraphStyle("v", parent=risk_val_style, textColor=C(colour))),
                ])
            return out

        colour_rows = _kv_coloured(risk_rows, {
            "Low risk": RISK_LOW, "Moderate risk": RISK_MODERATE, "High risk": RISK_HIGH,
        })
        risk_table = Table(colour_rows, colWidths=[70 * mm, 85 * mm], style=self._kv_style())
        story.append(risk_table)
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            "Risk assessments combine the weather-based severity model with a documented, bounded sentiment-fusion "
            "layer (upward-only, max +12). Methodology and model version are recorded with every prediction; see the "
            "HeatWatch AI model card (docs/model/model_card.md) for evaluation scope and limitations.", small))

        # ---- 3. Sentiment ----------------------------------------------------
        story.append(Paragraph("3 · Sentiment Analysis Summary", h2))
        story.append(HRFlowable(width="100%", thickness=0.7, color=C(BORDER), spaceAfter=5))
        s = summary["sentiment"]
        sent_rows = [
            ["Posts analysed", str(s["posts"])],
            ["Positive", str(s["positive"])],
            ["Neutral", str(s["neutral"])],
            ["Negative", str(s["negative"])],
            ["Heat-related posts", str(s["heat_related"])],
            ["Heat-related distress signals", str(s["distress"])],
            ["Average sentiment score", str(s["avg_score"]) if s["avg_score"] is not None else "n/a"],
        ]
        colour_rows = _kv_coloured(sent_rows, {
            "Positive": RISK_LOW, "Negative": RISK_HIGH,
        })
        story.append(Table(colour_rows, colWidths=[70 * mm, 85 * mm], style=self._kv_style()))
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            "Sentiment model: VADER (pretrained, English social-media lexicon; compound score in [-1, 1]). General "
            "sentiment is distinct from heat-related distress: the distress count includes only heat-relevant posts "
            "with health/impact vocabulary. Sentiment is a complementary signal, not a standalone severity measure.",
            small))

        # ---- 4. Alerts ---------------------------------------------------------
        story.append(Paragraph("4 · Alert Summary", h2))
        story.append(HRFlowable(width="100%", thickness=0.7, color=C(BORDER), spaceAfter=5))
        a_sum = summary["alerts"]
        alert_rows: list = [[
            Paragraph('<font color="#111827"><b>GENERATED (UTC)</b></font>', small),
            Paragraph('<font color="#111827"><b>LEVEL</b></font>', small),
            Paragraph('<font color="#111827"><b>SEVERITY</b></font>', small),
            Paragraph('<font color="#111827"><b>STATUS</b></font>', small),
        ]]
        level_colour = {"high": RISK_HIGH, "moderate": RISK_MODERATE, "low": RISK_LOW}
        status_colour = {"active": RISK_HIGH, "acknowledged": "#0284C7", "resolved": SLATE}
        for alert in data["alerts"][:14]:
            alert_rows.append([
                Paragraph(alert.generated_at.strftime("%Y-%m-%d %H:%M"), small),
                Paragraph(f'<font color="{level_colour.get(alert.risk_level, INK)}"><b>{alert.risk_level.upper()}</b></font>', small),
                Paragraph(f"{alert.severity_score:.0f}/100", small),
                Paragraph(f'<font color="{status_colour.get(alert.status, INK)}">{alert.status}</font>', small),
            ])
        if len(data["alerts"]) > 14:
            alert_rows.append([Paragraph(f"… {len(data['alerts']) - 14} further alert(s) in this period.", small),
                               "", "", ""])
        story.append(Table(alert_rows, colWidths=[45 * mm, 30 * mm, 30 * mm, 50 * mm], style=self._table_style()))
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            f"Total alerts in period: {a_sum['count']} (high: {a_sum['high']}, moderate: {a_sum['moderate']}). "
            f"All alerts are application-generated early warnings with cooldown and escalation policy — they are "
            f"not official government advisories.", small))

        # ---- 5. Methodology -----------------------------------------------------
        story.append(Spacer(1, 8))
        story.append(Paragraph("5 · Data Source and Methodology Notes", h2))
        story.append(HRFlowable(width="100%", thickness=0.7, color=C(BORDER), spaceAfter=5))
        provenance = _mode_labels(data["weather"])
        provenance_colour = (
            DEMO_VIOLET if "DEMO" in provenance and "LIVE" not in provenance
            else (NAVY if "LIVE" in provenance and "DEMO" not in provenance else "#B45309")
        )
        notes = [
            f'<font color="{provenance_colour}"><b>Data provenance: {provenance}</b></font> — records marked DEMO are '
            "seeded demonstration data and do not represent real observations or real public posts.",
            f"Weather observations: provider(s) {provenance}; units: temperature in degC, wind in km/h, pressure in hPa.",
            "Heat index: NWS Rothfusz regression with adjustments; reported only where applicability conditions hold.",
            "Sentiment model: VADER (pretrained, English social-media lexicon), compound score in [-1, 1].",
            "Severity model: weather-based scikit-learn RandomForest trained on the documented heat-index banding "
            "dataset, combined with a rule-based, bounded sentiment fusion layer. See the model card for evaluation "
            "metrics and limitations.",
            f"Report generated by {REPORT_BRAND}; every figure is derived exclusively from the database records "
            f"matching the selected filters.",
        ]
        for note in notes:
            story.append(Paragraph(f"• {note}", body))
            story.append(Spacer(1, 2))

        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

    @staticmethod
    def _kv_style():
        from reportlab.lib import colors
        from reportlab.platypus import TableStyle
        return TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, C_(BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ])

    @staticmethod
    def _table_style():
        from reportlab.lib import colors
        from reportlab.platypus import TableStyle
        return TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.3),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_(NAVY)),
            ("BACKGROUND", (0, 0), (-1, 0), C_("#F1F5F9")),
            ("GRID", (0, 0), (-1, -1), 0.4, C_(BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ])

    @staticmethod
    def _meta_style():
        from reportlab.lib import colors
        from reportlab.platypus import TableStyle
        return TableStyle([
            ("FONT", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
        ])

    # ----------------------------------------------------------------- CSV
    def _write_csv(self, path: Path, location: Location, data: dict) -> None:
        rows = []
        preds_by_time = {}
        for p in data["predictions"]:
            key = p.weather_observation_id
            preds_by_time.setdefault(key, []).append(p)
        alerts_by_prediction = {}
        for a in data["alerts"]:
            if a.prediction_id:
                alerts_by_prediction.setdefault(a.prediction_id, []).append(a)

        for w in data["weather"]:
            pred = (preds_by_time.get(w.id) or [None])[-1]
            alert = alerts_by_prediction.get(pred.id, [None])[-1] if pred else None
            rows.append({
                "location": location.display_name,
                "observed_at_utc": w.observed_at.isoformat(),
                "temperature_c": w.temperature_c,
                "humidity_pct": w.humidity_pct,
                "heat_index_c": w.heat_index_c if w.heat_index_c is not None else "",
                "wind_speed_kph": w.wind_speed_kph,
                "condition": w.condition_text,
                "risk_category": pred.risk_category if pred else "",
                "severity_score_0_100": pred.severity_score if pred else "",
                "prediction_methodology": pred.methodology if pred else "",
                "sentiment_adjustment": pred.sentiment_adjustment if pred else "",
                "alert_level": alert.risk_level if alert else "",
                "data_mode": w.data_mode,
            })

        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [
                "location", "observed_at_utc", "temperature_c", "humidity_pct", "heat_index_c",
                "wind_speed_kph", "condition", "risk_category", "severity_score_0_100",
                "prediction_methodology", "sentiment_adjustment", "alert_level", "data_mode",
            ])
            writer.writeheader()
            for row in rows[: self.config["REPORT_MAX_ROWS_CSV"]]:
                writer.writerow(row)

    def read_record(self, record: ReportRecord) -> tuple[Path, str, str]:
        path = Path(record.file_path)
        if not path.exists():
            raise FileNotFoundError("Report file is missing from storage.")
        mime = "application/pdf" if record.format == "pdf" else "text/csv"
        return path, mime, path.name


def C_(hex_: str):
    """Module-level colour helper usable inside static style builders."""
    from reportlab.lib import colors
    return colors.HexColor(hex_)
