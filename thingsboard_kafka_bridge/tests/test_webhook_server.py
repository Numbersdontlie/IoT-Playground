"""Tests for webhook server per specs/kafka_bridge.feature."""

import pytest
import json
from unittest.mock import MagicMock
from thingsboard_kafka_bridge.webhook_server import create_app, WebhookServer


class TestCreateApp:
    """Test Flask app creation."""

    def test_creates_flask_app(self):
        app = create_app()
        assert app is not None

    def test_routes_events_endpoint(self):
        app = create_app()
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/events" in rules

    def test_routes_healthz_endpoint(self):
        app = create_app()
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/healthz" in rules


class TestEventsEndpoint:
    """Test webhook event handling per specs/kafka_bridge.feature.

    Scenario: Bridge accepts webhook events from ThingsBoard
      When POST /events with telemetry data
      Then should respond with 202 Accepted
    """

    def test_returns_202_for_telemetry(self):
        mock_producer = MagicMock()
        mock_producer.publish_event.return_value = True

        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.post(
            "/events",
            data=json.dumps({
                "type": "POST_TELEMETRY_REQUEST",
                "body": {"temperature": 45.0},
            }),
            content_type="application/json",
        )
        assert response.status_code == 202

    def test_returns_202_for_alarm(self):
        mock_producer = MagicMock()
        mock_producer.publish_event.return_value = True

        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.post(
            "/events",
            data=json.dumps({
                "type": "ALARM",
                "body": {"alarm": "test"},
            }),
            content_type="application/json",
        )
        assert response.status_code == 202

    def test_returns_202_for_attribute(self):
        mock_producer = MagicMock()
        mock_producer.publish_event.return_value = True

        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.post(
            "/events",
            data=json.dumps({
                "type": "ATTRIBUTE_UPDATE",
                "body": {"attr": "value"},
            }),
            content_type="application/json",
        )
        assert response.status_code == 202

    def test_publishes_to_correct_topic(self):
        mock_producer = MagicMock()
        mock_producer.publish_event.return_value = True

        app = create_app(producer=mock_producer)
        client = app.test_client()

        client.post(
            "/events",
            data=json.dumps({"type": "ALARM"}),
            content_type="application/json",
        )
        mock_producer.publish_event.assert_called_once()
        call_args = mock_producer.publish_event.call_args
        assert call_args[0][0] == "ALARM"

    def test_forwards_payload(self):
        mock_producer = MagicMock()
        mock_producer.publish_event.return_value = True

        app = create_app(producer=mock_producer)
        client = app.test_client()

        payload = {
            "type": "POST_TELEMETRY_REQUEST",
            "entityId": {"type": "DEVICE", "id": "abc123"},
            "body": {"Temperature": 50.0},
        }
        client.post(
            "/events",
            data=json.dumps(payload),
            content_type="application/json",
        )
        mock_producer.publish_event.assert_called_once()
        call_args = mock_producer.publish_event.call_args
        assert call_args[0][1] == payload


class TestEventsEndpointInvalid:
    """Test invalid payload handling.

    Scenario: Bridge handles invalid payload
      When POST /events with malformed JSON
      Then should respond with 400 Bad Request
      And no message should be published to Kafka
    """

    def test_returns_400_for_invalid_json(self):
        mock_producer = MagicMock()
        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.post(
            "/events",
            data="not valid json {",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_returns_400_for_missing_type(self):
        mock_producer = MagicMock()
        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.post(
            "/events",
            data=json.dumps({"not_type": "value"}),
            content_type="application/json",
        )
        assert response.status_code == 400
        mock_producer.publish_event.assert_not_called()

    def test_no_publish_on_invalid_json(self):
        mock_producer = MagicMock()
        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.post(
            "/events",
            data="invalid",
            content_type="application/json",
        )
        assert response.status_code == 400
        mock_producer.publish_event.assert_not_called()


class TestHealthzEndpoint:
    """Test health check per specs/kafka_bridge.feature.

    Scenario: Bridge exposes health endpoint
      When GET /healthz
      Then should respond with 200 OK
      And indicate Kafka connectivity status
    """

    def test_returns_200(self):
        mock_producer = MagicMock()
        mock_producer.check_health.return_value = True
        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.get("/healthz")
        assert response.status_code == 200

    def test_returns_healthy_status(self):
        mock_producer = MagicMock()
        mock_producer.check_health.return_value = True
        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.get("/healthz")
        data = json.loads(response.data)
        assert data["status"] == "healthy"

    def test_returns_unhealthy_when_kafka_down(self):
        mock_producer = MagicMock()
        mock_producer.check_health.return_value = False
        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.get("/healthz")
        data = json.loads(response.data)
        assert data["status"] == "unhealthy"
        assert data["kafka"] == "disconnected"


class TestWebhookServerWrapper:
    """Test WebhookServer wrapper class."""

    def test_creates_app(self):
        server = WebhookServer()
        assert server.get_app() is not None

    def test_default_host_port(self):
        server = WebhookServer()
        assert server.host == "0.0.0.0"
        assert server.port == 8086

    def test_producer_property(self):
        server = WebhookServer()
        # Producer may be None if confluent-kafka not installed
        # Just verify it's set
        assert hasattr(server, 'producer')
