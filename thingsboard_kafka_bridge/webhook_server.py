"""ThingsBoard webhook server for Kafka bridge.

Receives webhook events from ThingsBoard and publishes to Kafka.
"""

import json
import logging
from typing import Optional, Dict, Any

from flask import Flask, request, jsonify

from thingsboard_kafka_bridge.kafka_producer import KafkaBridgeProducer

logger = logging.getLogger(__name__)

# Module-level singleton for the Kafka bridge producer
_producer: Optional[KafkaBridgeProducer] = None


def get_producer() -> Optional[KafkaBridgeProducer]:
    """Get or create the singleton Kafka bridge producer.

    Returns:
        KafkaBridgeProducer instance or None if not initialized.
    """
    return _producer


def set_producer(producer: KafkaBridgeProducer) -> None:
    """Set the singleton Kafka bridge producer.

    Args:
        producer: Kafka bridge producer instance.
    """
    global _producer
    _producer = producer


def clear_producer() -> None:
    """Clear the singleton Kafka bridge producer."""
    global _producer
    _producer = None


def create_app(
    producer: Optional[KafkaBridgeProducer] = None,
    bootstrap_servers: str = "localhost:9092",
    telemetry_topic: str = "thingsboard.telemetry",
    alarm_topic: str = "thingsboard.alarm",
    attribute_topic: str = "thingsboard.attributes",
) -> Flask:
    """Create Flask app for webhook server.

    If no producer is provided, creates a singleton producer instance.

    Args:
        producer: Optional pre-configured producer.
        bootstrap_servers: Kafka bootstrap servers.
        telemetry_topic: Kafka topic for telemetry.
        alarm_topic: Kafka topic for alarms.
        attribute_topic: Kafka topic for attributes.

    Returns:
        Configured Flask application.
    """
    global _producer

    app = Flask(__name__)
    app.config["DEBUG"] = False

    if producer is not None:
        _producer = producer
    elif _producer is None:
        _producer = KafkaBridgeProducer(
            telemetry_topic=telemetry_topic,
            alarm_topic=alarm_topic,
            attribute_topic=attribute_topic,
            bootstrap_servers=bootstrap_servers,
        )

    broker = get_producer()

    @app.route("/events", methods=["POST"])
    def handle_events():
        """Handle webhook events from ThingsBoard.

        Expects JSON body with ThingsBoard event payload.
        Event type is determined from payload's 'type' field.

        Returns:
            Response with status code.
        """
        broker = get_producer()
        if broker is None:
            return jsonify({"error": "Bridge not initialized"}), 503

        try:
            data = request.get_json(force=False, silent=False)
        except Exception as e:
            logger.warning("Invalid JSON: %s", e)
            return jsonify({"error": "Invalid JSON"}), 400

        if data is None:
            return jsonify({"error": "Missing or invalid JSON body"}), 400

        event_type = data.get("type")
        if not event_type:
            return jsonify({"error": "Missing event type"}), 400

        success = broker.publish_event(event_type, data)

        if success:
            return jsonify({"status": "accepted"}), 202
        else:
            return jsonify({"status": "failed", "error": "Kafka unavailable"}), 503

    @app.route("/healthz", methods=["GET"])
    def healthz():
        """Health check endpoint.

        Returns:
            Health status with Kafka connectivity.
        """
        broker = get_producer()
        if broker is None:
            return jsonify({
                "status": "unhealthy",
                "kafka": "disconnected",
                "reason": "bridge not initialized",
            }), 200

        healthy = broker.check_health()
        return jsonify({
            "status": "healthy" if healthy else "unhealthy",
            "kafka": "connected" if healthy else "disconnected",
        }), 200

    return app


class WebhookServer:
    """Wrapper around Flask webhook server for easier testing."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8086,
        producer: Optional[KafkaBridgeProducer] = None,
        **kwargs,
    ) -> None:
        """Initialize webhook server.

        Args:
            host: Bind address.
            port: Listen port.
            producer: Optional Kafka bridge producer.
            **kwargs: Additional arguments for create_app.
        """
        self.host = host
        self.port = port
        self.app = create_app(producer=producer, **kwargs)
        self._producer = get_producer()

    def get_app(self) -> Flask:
        """Get the Flask application instance.

        Returns:
            Flask app instance.
        """
        return self.app

    @property
    def producer(self) -> Optional[KafkaBridgeProducer]:
        """Get the Kafka bridge producer."""
        return self._producer

    @staticmethod
    def teardown() -> None:
        """Clear the singleton producer (useful for tests)."""
        clear_producer()
