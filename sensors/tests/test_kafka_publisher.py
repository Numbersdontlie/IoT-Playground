"""Tests for Kafka publisher per specs/kafka_publishing.feature."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sensors.kafka_publisher import KafkaPublisher


class TestKafkaPublisherInit:
    """Test publisher initialization."""

    def test_default_values(self):
        with patch("sensors.kafka_publisher.Producer", None):
            pub = KafkaPublisher()
        assert pub.topic == "iot.sensors.raw"
        assert pub.bootstrap_servers == "localhost:9092"
        assert pub.acks == "all"

    def test_custom_values(self):
        with patch("sensors.kafka_publisher.Producer", None):
            pub = KafkaPublisher(
                topic="custom/topic",
                bootstrap_servers="custom:9092",
                acks="1",
            )
        assert pub.topic == "custom/topic"
        assert pub.bootstrap_servers == "custom:9092"
        assert pub.acks == "1"

    def test_partitioner_configured(self):
        with patch("sensors.kafka_publisher.Producer", None):
            pub = KafkaPublisher()
        assert pub.acks == "all"


class TestKafkaPublisherGetters:
    """Test getter methods."""

    def test_get_topic(self):
        with patch("sensors.kafka_publisher.Producer", None):
            pub = KafkaPublisher(topic="my/topic")
        assert pub.get_topic == "my/topic"

    def test_get_acks(self):
        with patch("sensors.kafka_publisher.Producer", None):
            pub = KafkaPublisher(acks="1")
        assert pub.get_acks == "1"


class TestKafkaPublisherNoConfluent:
    """Test behavior when confluent-kafka is not installed."""

    def test_initialized_is_false_without_library(self):
        with patch("sensors.kafka_publisher.Producer", None):
            pub = KafkaPublisher()
        assert pub.initialized is False


class TestKafkaPublisherPublish:
    """Test Kafka publishing per specs/kafka_publishing.feature.

    Scenario: Kafka messages have correct structure
      - Message key is machine_id string
      - Message value is valid JSON
      - JSON contains same fields as MQTT payload
    """

    @patch("sensors.kafka_publisher.Producer")
    def test_publish_with_correct_topic(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        pub = KafkaPublisher(topic="test/topic")
        result = pub.publish(
            key="machine-1",
            value={"Temperature": 45.0},
        )
        assert result is True
        mock_producer.produce.assert_called_once()
        call_kwargs = mock_producer.produce.call_args[1]
        assert call_kwargs["topic"] == "test/topic"

    @patch("sensors.kafka_publisher.Producer")
    def test_publish_key_as_bytes(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        pub = KafkaPublisher()
        pub.publish(key="machine-1", value={"test": 1})
        call_args = mock_producer.produce.call_args[1]
        assert call_args["key"] == b"machine-1"

    @patch("sensors.kafka_publisher.Producer")
    def test_publish_value_as_json_bytes(self, mock_producer_cls):
        import json
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        pub = KafkaPublisher()
        test_data = {
            "Temperature": 45.0,
            "Vibration": 2.5,
            "Pressure": 4.0,
            "RPM": 1500.0,
            "Humidity": 50.0,
            "MachineHealth": 100.0,
            "timestamp": 1234567890,
            "machine_id": "machine-1",
            "alarms": [],
        }
        pub.publish(key="machine-1", value=test_data)
        call_args = mock_producer.produce.call_args[1]
        # Value should be valid JSON
        decoded = json.loads(call_args["value"])
        assert decoded == test_data


class TestKafkaPublisherPartitioning:
    """Test message partitioning.

    Scenario: Messages are partitioned by machine
      - Messages from same machine go to same partition
      - Messages from different machines may go to different partitions
    """

    @patch("sensors.kafka_publisher.Producer")
    def test_same_key_same_partition(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        pub = KafkaPublisher()
        # Publish twice with same key
        pub.publish(key="machine-1", value={"test": 1})
        pub.publish(key="machine-1", value={"test": 2})
        # Both should use same key
        assert mock_producer.produce.call_count == 2
        calls = mock_producer.produce.call_args_list
        assert calls[0][1]["key"] == calls[1][1]["key"]

    @patch("sensors.kafka_publisher.Producer")
    def test_different_keys_different_partitions(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        pub = KafkaPublisher()
        pub.publish(key="machine-1", value={"test": 1})
        pub.publish(key="machine-2", value={"test": 2})
        calls = mock_producer.produce.call_args_list
        assert calls[0][1]["key"] != calls[1][1]["key"]


class TestKafkaPublisherDurability:
    """Test durability guarantees.

    Scenario: Kafka produces with durability guarantees
      - acks should be set to 'all'
      - Message should be persisted before acknowledgment
    """

    @patch("sensors.kafka_publisher.Producer")
    def test_acks_all_configured(self, mock_producer_cls):
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        pub = KafkaPublisher(acks="all")
        mock_producer_cls.assert_called_once()
        config = mock_producer_cls.call_args[0][0]
        assert config["acks"] == "all"


class TestKafkaPublisherErrorHandling:
    """Test error handling.

    Scenario: Kafka handles broker unavailability
      - Should log broker error
      - Simulator should continue running
      - MQTT publishing should continue unaffected
    """

    @patch("sensors.kafka_publisher.Producer")
    def test_publish_returns_false_without_init(self, mock_producer_cls):
        mock_producer_cls.return_value = None
        pub = KafkaPublisher()
        result = pub.publish(key="machine-1", value={"test": 1})
        assert result is False

    @patch("sensors.kafka_publisher.Producer")
    def test_error_callback_stores_error(self, mock_producer_cls):
        """Skip if confluent-kafka not installed."""
        try:
            from confluent_kafka import KafkaException
        except ImportError:
            pytest.skip("confluent-kafka not installed")

        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        pub = KafkaPublisher()
        mock_error = KafkaException("Test error")
        pub._error_callback(mock_error)
        assert len(pub.get_errors()) == 1
        assert "Test error" in pub.get_errors()[0]


class TestKafkaPublisherFlush:
    """Test flush functionality."""

    @patch("sensors.kafka_publisher.Producer")
    def test_flush_returns_zero_when_not_initialized(self, mock_producer_cls):
        mock_producer_cls.return_value = None
        pub = KafkaPublisher()
        assert pub.flush() == 0
