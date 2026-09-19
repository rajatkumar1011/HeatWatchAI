"""Standalone scheduler process (run: python run_scheduler.py).

Background collection deliberately runs in its own process so it is never
duplicated when the web app runs with multiple workers (APScheduler jobs
here are the single source of periodic execution). Jobs are idempotent:
duplicate provider observations/posts are suppressed at ingestion time.

Requires the SQLAlchemy models to exist (migrations applied). The scheduler
shares the same DATABASE_URL configuration as the web app.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.extensions import db
from app.models import Location
from app.services.monitoring_service import MonitoringService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("heatwatch.scheduler")


def main() -> None:
    app = create_app()

    with app.app_context():
        monitored = list(db.session.execute(
            Location.__table__.select().where(Location.__table__.c.is_monitored == True)  # noqa: E712
        ).mappings())
        config = app.config
        weather_minutes = config["WEATHER_COLLECTION_MINUTES"]
        social_minutes = config["SOCIAL_COLLECTION_MINUTES"]
        logger.info("Scheduler starting: %d monitored locations", len(monitored))

    monitoring = MonitoringService(app.config)

    def weather_job() -> None:
        with app.app_context():
            for location in db.session.query(Location).filter(Location.is_monitored.is_(True)).all():
                monitoring.weather.fetch_and_store(location, trigger="scheduler")
            logger.info("Scheduled weather collection finished")

    def social_job() -> None:
        with app.app_context():
            for location in db.session.query(Location).filter(Location.is_monitored.is_(True)).all():
                monitoring.run_pipeline(location, trigger="scheduler", collect_social=True)
            logger.info("Scheduled social+prediction pipeline finished")

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(weather_job, "interval", minutes=weather_minutes, id="weather",
                      max_instances=1, coalesce=True, next_run_time=None)
    scheduler.add_job(social_job, "interval", minutes=max(social_minutes, 15), id="social_pipeline",
                      max_instances=1, coalesce=True)

    logger.info("Starting scheduler: weather every %d min, pipeline every %d min (Ctrl+C to stop)",
                weather_minutes, max(social_minutes, 15))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
