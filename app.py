# app.py
"""
Flask application entry point.
Local dashboard for the Visiotech -> Amazon flow plus the background
scheduler that pushes price/stock updates on a cron.
"""
from __future__ import annotations

import atexit
import logging
from threading import Thread

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from config.settings import settings
from src import db
from src.core.pricing import pricing_engine
from src.jobs.create_job import approve, send_approved, skip
from src.jobs.scan_job import ingest_catalog, scan_matches
from src.jobs.sync_job import run_sync

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = settings.secret_key

# Make sure the DB exists when the process starts.
db.init()


# ---------------- helpers -----------------------------------------------------

# In-process state for the scan progress bar. Single-user app so this is fine.
_scan_state: dict = {"running": False, "done": 0, "total": 0, "summary": None}


def _run_scan_async(only_unscanned: bool, limit):
    _scan_state.update(running=True, done=0, total=0, summary=None)

    def cb(done, total):
        _scan_state["done"] = done
        _scan_state["total"] = total

    try:
        summary = scan_matches(only_unscanned=only_unscanned, limit=limit, progress_cb=cb)
        _scan_state["summary"] = summary
    except Exception as exc:
        logger.exception("scan failed")
        _scan_state["summary"] = {"error": str(exc)}
    finally:
        _scan_state["running"] = False


# ---------------- dashboard ---------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    status_filter = request.args.get("status", "all")
    search = request.args.get("q", "").strip() or None
    products = db.list_products(status_filter=status_filter, search=search)
    counts = db.status_counts()
    return render_template(
        "dashboard.html",
        products=products,
        counts=counts,
        status_filter=status_filter,
        search=search or "",
        scan_state=_scan_state,
    )


@app.route("/ingest", methods=["POST"])
def ingest():
    """Reload products from the Visiotech XLSX into the local DB."""
    try:
        summary = ingest_catalog()
        flash(f"Catálogo Visiotech carregado: {summary['ingested']} produtos.", "success")
    except Exception as exc:
        logger.exception("ingest failed")
        flash(f"Erro a carregar XLSX: {exc}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/scan", methods=["POST"])
def scan():
    """Kick off a background scan: existence + EAN + title matching."""
    if _scan_state["running"]:
        flash("Já existe uma análise a correr.", "warning")
        return redirect(url_for("dashboard"))
    only_unscanned = request.form.get("force") != "1"
    limit_raw = request.form.get("limit", "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else None
    Thread(target=_run_scan_async, args=(only_unscanned, limit), daemon=True).start()
    flash("Análise iniciada em background.", "info")
    return redirect(url_for("dashboard"))


@app.route("/scan/status")
def scan_status():
    return jsonify(_scan_state)


# ---------------- per-SKU actions --------------------------------------------

@app.route("/products/<sku>/review")
def review(sku):
    product_rows = db.list_products()
    product = next((p for p in product_rows if p["sku"] == sku), None)
    if not product:
        flash(f"SKU {sku} não encontrado.", "warning")
        return redirect(url_for("dashboard"))
    candidates = db.get_candidates(sku)
    return render_template("review.html", product=product, candidates=candidates)


@app.route("/products/<sku>/approve", methods=["POST"])
def approve_one(sku):
    asin = request.form.get("asin", "").strip()
    if not asin:
        flash("Falta ASIN para aprovar.", "danger")
        return redirect(url_for("review", sku=sku))
    approve(sku=sku, asin=asin)
    flash(f"{sku} aprovado para criação na Amazon (ASIN {asin}).", "success")
    return redirect(url_for("dashboard"))


@app.route("/products/<sku>/skip", methods=["POST"])
def skip_one(sku):
    skip(sku)
    flash(f"{sku} marcado como ignorado.", "info")
    return redirect(url_for("dashboard"))


@app.route("/products/bulk-approve", methods=["POST"])
def bulk_approve():
    """Approve every selected SKU that has an EAN match (uses that ASIN)."""
    skus = request.form.getlist("sku")
    rows = {r["sku"]: r for r in db.list_products()}
    approved = 0
    skipped = 0
    for sku in skus:
        r = rows.get(sku)
        if not r:
            continue
        if r["status"] == "ean_match" and r["asin"]:
            approve(sku=sku, asin=r["asin"])
            approved += 1
        else:
            skipped += 1
    flash(f"Aprovados {approved} SKUs. Ignorados {skipped} (sem EAN match).", "success")
    return redirect(url_for("dashboard"))


@app.route("/create-all", methods=["POST"])
def create_all():
    """Send all approved SKUs to Amazon as new listings."""
    summary = send_approved()
    flash(
        f"Criação: {summary['created']} listagens criadas, {summary['failed']} falharam.",
        "success" if summary["failed"] == 0 else "warning",
    )
    return redirect(url_for("dashboard"))


# ---------------- API endpoints (legacy / smoke) -----------------------------

@app.route("/health")
def health():
    try:
        settings.load_rules()
        test_result = pricing_engine.calculate_price(cost=10.0)
        return jsonify(
            {
                "status": "healthy",
                "marketplace": settings.marketplace_id,
                "simulate": settings.simulate_mode,
                "pricing_sample": {
                    "cost": test_result.cost,
                    "floor_price": test_result.floor_price,
                    "margin": f"{test_result.margin_used * 100}%",
                },
            }
        )
    except Exception as e:
        logger.exception("Health check failed")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(_e):
    logger.exception("Internal server error")
    return jsonify({"error": "Internal server error"}), 500


# ---------------- scheduler --------------------------------------------------

def _scheduled_sync():
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


def _start_scheduler():
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


_start_scheduler()


if __name__ == "__main__":
    if settings.flask_env == "development":
        app.run(host="0.0.0.0", port=settings.port, debug=True, use_reloader=False)
    else:
        from waitress import serve

        logger.info(f"Starting Waitress server on port {settings.port}")
        serve(app, host="0.0.0.0", port=settings.port, threads=4)
