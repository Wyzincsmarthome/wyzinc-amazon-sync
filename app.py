# app.py
"""
Flask application entry point.
Runs the web service and an in-process scheduler that triggers the Amazon
sync job on a cron schedule.
"""
from __future__ import annotations

import atexit
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, jsonify

from config.settings import settings
from src.core.pricing import pricing_engine
from src.jobs.sync_job import run_sync

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = settings.secret_key


@app.route("/")
def index():
    return jsonify(
        {
            "status": "ok",
            "service": "wyzinc-amazon-sync",
            "version": "1.1.0",
            "environment": settings.flask_env,
            "simulate_mode": settings.simulate_mode,
        }
    )


@app.route("/health")
def health():
    try:
        settings.load_rules()
        test_result = pricing_engine.calculate_price(cost=10.0)
        return jsonify(
            {
                "status": "healthy",
                "checks": {"settings": "ok", "pricing_engine": "ok", "rules_loaded": "ok"},
                "config": {
                    "marketplace": settings.marketplace_id,
                    "simulate": settings.simulate_mode,
                    "storage": settings.storage_provider,
                    "sync_cron": settings.sync_cron,
                    "sync_source": settings.sync_source,
                },
                "test_calculation": {
                    "cost": test_result.cost,
                    "floor_price": test_result.floor_price,
                    "margin": f"{test_result.margin_used * 100}%",
                },
            }
        )
    except Exception as e:
        logger.exception("Health check failed")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.route("/test/pricing")
def test_pricing():
    scenarios = [
        {"cost": 10.0, "competitor": None},
        {"cost": 10.0, "competitor": 25.0},
        {"cost": 50.0, "competitor": 70.0},
        {"cost": 100.0, "competitor": None},
    ]
    results = []
    for s in scenarios:
        r = pricing_engine.calculate_price(cost=s["cost"], competitor_price=s.get("competitor"))
        results.append(
            {
                "input": s,
                "output": {
                    "floor_price": r.floor_price,
                    "final_price": r.final_price,
                    "margin_used": f"{r.margin_used * 100}%",
                },
            }
        )
    return jsonify({"scenarios": results})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    logger.exception("Internal server error")
    return jsonify({"error": "Internal server error"}), 500


def _scheduled_sync():
    """Wrapper called by APScheduler. Never let exceptions escape the scheduler."""
    try:
        logger.info("Scheduled sync starting (source=%s)", settings.sync_source)
        summary = run_sync(
            source=settings.sync_source,
            input_file=settings.sync_input_file or None,
        )
        logger.info(
            "Scheduled sync finished: built=%d, batches=%d",
            summary.get("updates_built", 0),
            len(summary.get("feeds", [])),
        )
    except Exception:
        logger.exception("Scheduled sync failed")


def _start_scheduler() -> BackgroundScheduler | None:
    if not settings.sync_enabled:
        logger.info("Scheduler disabled (SYNC_ENABLED=false)")
        return None
    scheduler = BackgroundScheduler(timezone="Europe/Madrid")
    scheduler.add_job(
        _scheduled_sync,
        CronTrigger.from_crontab(settings.sync_cron, timezone="Europe/Madrid"),
        id="amazon_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))
    logger.info("Scheduler started with cron='%s'", settings.sync_cron)
    return scheduler


# Start the scheduler when the WSGI server imports this module.
_start_scheduler()


if __name__ == "__main__":
    if settings.flask_env == "development":
        # When running with debug=True Flask reloads the module twice; the
        # WERKZEUG_RUN_MAIN guard above prevents double-scheduling because the
        # second import happens in a child process.
        app.run(host="0.0.0.0", port=settings.port, debug=True, use_reloader=False)
    else:
        from waitress import serve

        logger.info(f"Starting Waitress server on port {settings.port}")
        serve(app, host="0.0.0.0", port=settings.port, threads=4)
