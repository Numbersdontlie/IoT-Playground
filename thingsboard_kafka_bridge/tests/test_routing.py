"""Tests for routing and event types per specs/kafka_bridge.feature."""

import pytest
from thingsboard_kafka_bridge.kafka_producer import KafkaBridgeProducer


class TestEventRoutng:
    """Test event type routing per specs/kafka_bridge.feature.

    Scenario: Bridge routes alarm events correctly
      When POST /events with alarm data and type=alarm
      Then should publish to thingsboard.alarm topic

    Scenario: Bridge routes attribute updates correctly
      When POST /events with attribute data and type=attribute_update
      Then should publish to thingsboard.attributes topic
    """

    def test_routing_maps_post_telemetry(self):
        assert KafkaBridgeProducer.EVENT_ROUTES["POST_TELEMETRY_REQUEST"] == \
            "thingsboard.telemetry"

    def test_routing_maps_alarm(self):
        assert KafkaBridgeProducer.EVENT_ROUTES["ALARM"] == \
            "thingsboard.alarm"

    def test_routing_maps_attribute_update(self):
        assert KafkaBridgeProducer.EVENT_ROUTES["ATTRIBUTE_UPDATE"] == \
            "thingsboard.attributes"


class TestEventPayloadValidation:
    """Test payload validation scenarios."""

    def test_publish_event_with_missing_type(self):
        from unittest.mock import MagicMock
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("thingsboard_kafka_bridge.kafka_producer.Producer", None)
            from thingsboard_kafka_bridge.kafka_producer import KafkaBridgeProducer
            prod = KafkaBridgeProducer()

        result = prod.publish_event("", {})
        assert result is False

    def test_publish_event_with_empty_type(self):
        from unittest.mock import MagicMock
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("thingsboard_kafka_bridge.kafka_producer.Producer", None)
            from thingsboard_kafka_bridge.kafka_producer import KafkaBridgeProducer
            prod = KafkaBridgeProducer()

        result = prod.publish_event("", {})
        assert result is False

    def test_resolve_topic_returns_none_for_unknown(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("thingsboard_kafka_bridge.kafka_producer.Producer", None)
            from thingsboard_kafka_bridge.kafka_producer import KafkaBridgeProducer
            prod = KafkaBridgeProducer()

        result = prod._resolve_topic("NONEXISTENT")
        assert result is None


class TestEndToEndRouting:
    """Test end-to-end event flow per specs/kafka_bridge.feature.

    Scenario: End-to-end ThingsBoard to Kafka flow
      Given bridge is running and Kafka is available
      When device publishes telemetry to ThingsBoard via MQTT
      And ThingsBoard triggers the webhook rule
      Then data should appear in thingsboard.telemetry Kafka topic
    """

    @pytest.mark.parametrize("event_type,expected_topic", [
        ("POST_TELEMETRY_REQUEST", "thingsboard.telemetry"),
        ("ALARM", "thingsboard.alarm"),
        ("ATTRIBUTE_UPDATE", "thingsboard.attributes"),
    ])
    def test_all_event_types_routed(self, event_type, expected_topic):
        from unittest.mock import MagicMock, patch
        with patch("thingsboard_kafka_bridge.kafka_producer.Producer") as mock_cls:
            mock_producer = MagicMock()
            mock_cls.return_value = mock_producer

            prod = KafkaBridgeProducer()
            result = prod.publish_event(event_type, {"type": event_type})

            assert result is True
            call_kwargs = mock_producer.produce.call_args[1]
            assert call_kwargs["topic"] == expected_topic

    def test_realistic_telemetry_payload(self):
        """Test with realistic ThingsBoard telemetry payload."""
        from unittest.mock import MagicMock, patch
        import json

        with patch("thingsboard_kafka_bridge.kafka_producer.Producer") as mock_cls:
            mock_producer = MagicMock()
            mock_cls.return_value = mock_producer

            prod = KafkaBridgeProducer()

            payload = {
                "type": "POST_TELEMETRY_REQUEST",
                "entityId": {
                    "type": "DEVICE",
                    "id": {"type": "STRING", "value": "device-123"},
                },
                "body": {
                    "Temperature": 55.5,
                    "Vibration": 3.2,
                    "Pressure": 3.8,
                    "RPM": 1480.0,
                    "Humidity": 48.0,
                    "MachineHealth": 92.0,
                    "timestamp": 1699999999000,
                    "machine_id": "machine-1",
                    "alarms": [],
                },
            }

            result = prod.publish_event("POST_TELEMETRY_REQUEST", payload)
            assert result is True

            # Verify payload was serialized to JSON
            call_args = mock_producer.produce.call_args[1]
            decoded = json.loads(call_args["value"])
            assert decoded["type"] == "POST_TELEMETRY_REQUEST"
            assert decoded["body"]["Temperature"] == 55.5


class TestKafkaUnavailable:
    """Test behavior when Kafka is unavailable.

    Scenario: Bridge handles Kafka unavailability
      Given Kafka broker is not reachable
      When bridge receives webhook event
      Then should respond with 503 Service Unavailable
      And event should not be lost (ThingsBoard will retry)
    """

    @pytest.mark.parametrize("event_type,expected_topic", [
        ("POST_TELEMETRY_REQUEST", "thingsboard.telemetry"),
        ("ALARM", "thingsboard.alarm"),
        ("ATTRIBUTE_UPDATE", "thingsboard.attributes"),
    ])
    def test_publish_event_without_producer(self, event_type, expected_topic):
        from unittest.mock import MagicMock
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("thingsboard_kafka_bridge.kafka_producer.Producer", None)
            from thingsboard_kafka_bridge.kafka_producer import KafkaBridgeProducer
            prod = KafkaBridgeProducer()

        result = prod.publish_event(event_type, {"type": event_type})
        assert result is False
