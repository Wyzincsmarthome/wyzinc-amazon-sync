# app.py
"""
Flask application entry point.
Minimal version for initial deployment testing.
"""
from __future__ import annotations

import logging

from flask import Flask, jsonify
from waitress import serve

from config.settings import settings
from src.core.pricing import pricing_engine

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = settings.secret_key


@app.route("/")
def index():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "ok",
            "service": "wyzinc-amazon-sync",
            "version": "1.0.0",
            "environment": settings.flask_env,
            "simulate_mode": settings.simulate_mode,
        }
    )


@app.route("/health")
def health():
    """Detailed health check."""
    try:
        # Test settings loading
        rules = settings.load_rules()
        
        # Test pricing engine
        test_result = pricing_engine.calculate_price(cost=10.0)
        
        return jsonify(
            {
                "status": "healthy",
                "checks": {
                    "settings": "ok",
                    "pricing_engine": "ok",
                    "rules_loaded": "ok",
                },
                "config": {
                    "marketplace": settings.marketplace_id,
                    "simulate": settings.simulate_mode,
                    "storage": settings.storage_provider,
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
    """Test pricing calculations with multiple scenarios."""
    scenarios = [
        {"cost": 10.0, "competitor": None},
        {"cost": 10.0, "competitor": 25.0},
        {"cost": 50.0, "competitor": 70.0},
        {"cost": 100.0, "competitor": None},
    ]
    
    results = []
    for scenario in scenarios:
        result = pricing_engine.calculate_price(
            cost=scenario["cost"],
            competitor_price=scenario.get("competitor"),
        )
        results.append(
            {
                "input": scenario,
                "output": {
                    "floor_price": result.floor_price,
                    "final_price": result.final_price,
                    "margin_used": f"{result.margin_used * 100}%",
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


if __name__ == "__main__":
    if settings.flask_env == "development":
        # Development: Flask's built-in server with auto-reload
        app.run(host="0.0.0.0", port=settings.port, debug=True)
    else:
        # Production: Waitress WSGI server
        logger.info(f"Starting Waitress server on port {settings.port}")
        serve(app, host="0.0.0.0", port=settings.port, threads=4)
