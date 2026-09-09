"""Tests for bridge Kafka producer per specs/kafka_bridge.feature."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from thingsboard_kafka_bridge.kafka_producer import KafkaBridgeProducer


class TestKafkaBridgeProducerInit:
    """Test producer initialization."""

    def test_default_topics(self):
        with patch("thingsboard_kafka_bridge.kafka_producer.Producer", None):
            prod = KafkaBridgeProducer()
        assert prod.telemetry_topic == "thingsboard.telemetry"
        assert prod.alarm_topic == "thingsboard.alarm"
        assert prod.attribute_topic == "thingsboard.attributes"
        assert prod.bootstrap_servers == "localhost:9092"

    def test_custom_topics(self):
        with patch("thingsboard_kafka_bridge.kafka_producer.Producer", None):
            prod = KafkaBridgeProducer(
                telemetry_topic="custom.telemetry",
                alarm_topic="custom.alarm",
                attribute_topic="custom.attributes",
                bootstrap_servers="custom:9092",
            )
        assert prod.telemetry_topic == "custom.telemetry"
        assert prod.alarm_topic == "custom.alarm"
        assert prod.attribute_topic == "custom.attributes"
        assert prod.bootstrap_servers == "custom:9092"


class TestKafkaBridgeProducerRoutes:
    """Test event routing per specs/kafka_bridge.feature.

    Event Routing:
      | POST_TELEMETRY_REQUEST | thingsboard.telemetry |
      | ALARM | thingsboard.alarm |
      | ATTRIBUTE_UPDATE | thingsboard.attributes |
    """

    def test_telemetry_event_type(self):
        event_type = "POST_TELEMETRY_REQUEST"
        topic = KafkaBridgeProducer.EVENT_ROUTES[event_type]
        assert topic == "thingsboard.telemetry"

    def test_alarm_event_type(self):
        event_type = "ALARM"
        topic = KafkaBridgeProducer.EVENT_ROUTES[event_type]
        assert topic == "thingsboard.alarm"

    def test_attribute_event_type(self):
        event_type = "ATTRIBUTE_UPDATE"
        topic = KafkaBridgeProducer.EVENT_ROUTES[event_type]
        assert topic == "thingsboard.attributes"

    def test_unknown_event_type_returns_none(self):
        with patch("thingsboard_kafka_bridge.kafka_producer.Producer", None):
            prod = KafkaBridgeProducer()
        topic = prod._resolve_topic("UNKNOWN_TYPE")
        assert topic is None

    def test_all_expected_routes_exist(self):
        assert "POST_TELEMETRY_REQUEST" in KafkaBridgeProducer.EVENT_ROUTES
        assert "ALARM" in KafkaBridgeProducer.EVENT_ROUTES
        assert "ATTRIBUTE_UPDATE" in KafkaBridgeProducer.EVENT_ROUTES


class TestKafkaBridgeProducerPublish:
    """Test event publishing."""

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_publishes_to_correct_topic(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        result = prod.publish_event(
            "POST_TELEMETRY_REQUEST",
            {"type": "POST_TELEMETRY_REQUEST", "data": "test"}
        )
        assert result is True
        mock_producer.produce.assert_called_once()
        call_kwargs = mock_producer.produce.call_args[1]
        assert call_kwargs["topic"] == "thingsboard.telemetry"

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_alarm_publishes_to_alarm_topic(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        prod.publish_event("ALARM", {"type": "ALARM"})
        call_kwargs = mock_producer.produce.call_args[1]
        assert call_kwargs["topic"] == "thingsboard.alarm"

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_attribute_publishes_to_attribute_topic(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        prod.publish_event(
            "ATTRIBUTE_UPDATE",
            {"type": "ATTRIBUTE_UPDATE"}
        )
        call_kwargs = mock_producer.produce.call_args[1]
        assert call_kwargs["topic"] == "thingsboard.attributes"

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_publish_payload_as_json(self, mock_producer_cls):
        import json
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        test_data = {"type": "POST_TELEMETRY_REQUEST", "data": "value"}
        prod.publish_event("POST_TELEMETRY_REQUEST", test_data)
        call_args = mock_producer.produce.call_args[1]
        decoded = json.loads(call_args["value"])
        assert decoded == test_data

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_publish_unknown_event_type_fails(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        result = prod.publish_event("UNKNOWN_TYPE", {"type": "UNKNOWN"})
        assert result is False


class TestKafkaBridgeProducerHealth:
    """Test health checks per specs/kafka_bridge.feature.

    Scenario: Bridge exposes health endpoint
      When GET /healthz
      Then should respond with 200 OK
      And indicate Kafka connectivity status
    """

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_healthy_when_initialized(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        assert prod.is_healthy is True

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer", None)
    def test_unhealthy_without_library(self):
        prod = KafkaBridgeProducer()
        assert prod.is_healthy is False

    def test_check_health_method(self):
        with patch("thingsboard_kafka_bridge.kafka_producer.Producer", None):
            prod = KafkaBridgeProducer()
        # Not healthy since Producer is None
        assert prod.check_health() is False


class TestKafkaBridgeProducerErrors:
    """Test error handling per specs/kafka_bridge.feature.

    Scenario: Bridge handles Kafka unavailability
      Given Kafka broker is not reachable
      When bridge receives webhook event
      Then should respond with 503 Service Unavailable
    """

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_publish_fails_without_init(self, mock_producer_cls):
        mock_producer_cls.return_value = None
        prod = KafkaBridgeProducer()
        result = prod.publish_event("ALARM", {"type": "ALARM"})
        assert result is False

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_error_callback_sets_unhealthy(self, mock_producer_cls):
        """Skip if confluent-kafka not installed."""
        try:
            from confluent_kafka import KafkaException
        except ImportError:
            pytest.skip("confluent-kafka not installed")

        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        mock_error = KafkaException("Test error")
        prod._error_callback(mock_error)
        assert prod.is_healthy is False


class TestKafkaBridgeProducerConfig:
    """Test configuration."""

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_acks_all_configured(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        config = mock_producer_cls.call_args[0][0]
        assert config["acks"] == "all"
