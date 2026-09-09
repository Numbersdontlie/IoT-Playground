"""Tests for MQTT publisher per specs/mqtt_publishing.feature."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sensors.mqtt_publisher import MQTTPublisher


class TestMQTTPublisherInit:
    """Test publisher initialization."""

    def test_default_values(self):
        pub = MQTTPublisher()
        assert pub.broker == "localhost"
        assert pub.port == 1884
        assert pub.topic == "v1/devices/me/telemetry"
        assert pub.qos == 1
        assert pub.token == ""

    def test_custom_values(self):
        pub = MQTTPublisher(
            broker="custom-broker",
            port=1234,
            topic="custom/topic",
            qos=0,
            token="device-token-123",
        )
        assert pub.broker == "custom-broker"
        assert pub.port == 1234
        assert pub.topic == "custom/topic"
        assert pub.qos == 0
        assert pub.token == "device-token-123"

    def test_default_backoff_values(self):
        pub = MQTTPublisher()
        assert pub.backoff_base == 1.0
        assert pub.backoff_max == 30.0


class TestMQTTPublisherGetters:
    """Test getter methods."""

    def test_get_topic(self):
        pub = MQTTPublisher(topic="my/topic")
        assert pub.get_topic() == "my/topic"

    def test_get_qos(self):
        pub = MQTTPublisher(qos=2)
        assert pub.get_qos() == 2


class TestMQTTPublisherNoPaho:
    """Test behavior when paho-mqtt is not installed."""

    def test_connect_fails_without_paho(self):
        pub = MQTTPublisher()
        result = pub.connect()
        assert result is False


class TestMQTTPublisherConnect:
    """Test MQTT connection per specs/mqtt_publishing.feature."""

    @patch("sensors.mqtt_publisher.mqtt")
    def test_connect_uses_token_from_init(self, mock_mqtt):
        mock_client = MagicMock()
        mock_mqtt.Client.return_value = mock_client
        pub = MQTTPublisher(token="my-token")
        result = pub.connect()
        assert result is True
        mock_mqtt.Client.assert_called_once()
        mock_client.username_pw_set.assert_called_once_with("my-token")

    @patch("sensors.mqtt_publisher.mqtt")
    def test_connect_creates_client(self, mock_mqtt):
        mock_client = MagicMock()
        mock_mqtt.Client.return_value = mock_client
        pub = MQTTPublisher()
        result = pub.connect()
        assert result is True
        mock_mqtt.Client.assert_called_once()
        mock_client.username_pw_set.assert_called_once_with("")

    @patch("sensors.mqtt_publisher.mqtt")
    def test_connect_sends_callback_setup(self, mock_mqtt):
        mock_client = MagicMock()
        mock_mqtt.Client.return_value = mock_client
        pub = MQTTPublisher()
        pub.connect()
        assert mock_client.on_connect is not None
        assert mock_client.on_disconnect is not None


class TestMQTTPublisherPublish:
    """Test MQTT publishing per specs/mqtt_publishing.feature.

    Scenario: Telemetry payload contains all required fields
      Fields: Temperature, Vibration, Pressure, RPM, Humidity,
              MachineHealth, timestamp, machine_id
    """

    @patch("sensors.mqtt_publisher.mqtt")
    def test_publish_sends_json(self, mock_mqtt):
        mock_client = MagicMock()
        mock_client.publish.return_value.wait_for_publish.return_value = True
        mock_client.publish.return_value.is_published.return_value = True
        mock_mqtt.Client.return_value = mock_client

        pub = MQTTPublisher()
        pub.connect()

        payload = {
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
        result = pub.publish(payload)
        assert result is True

    @patch("sensors.mqtt_publisher.mqtt")
    def test_publish_with_correct_topic(self, mock_mqtt):
        mock_client = MagicMock()
        mock_client.publish.return_value.wait_for_publish.return_value = True
        mock_client.publish.return_value.is_published.return_value = True
        mock_mqtt.Client.return_value = mock_client

        pub = MQTTPublisher(topic="v1/devices/me/telemetry")
        pub.connect()
        pub.publish({"test": 1})
        mock_client.publish.assert_called_once()
        call_args = mock_client.publish.call_args
        assert call_args[0][0] == "v1/devices/me/telemetry"

    @patch("sensors.mqtt_publisher.mqtt")
    def test_publish_with_qos_1(self, mock_mqtt):
        mock_client = MagicMock()
        mock_client.publish.return_value.wait_for_publish.return_value = True
        mock_client.publish.return_value.is_published.return_value = True
        mock_mqtt.Client.return_value = mock_client

        pub = MQTTPublisher(qos=1)
        pub.connect()
        pub.publish({"test": 1})
        mock_client.publish.assert_called_once()
        call_kwargs = mock_client.publish.call_args[1]
        assert call_kwargs["qos"] == 1


class TestMQTTPublisherDisconnect:
    """Test disconnection."""

    @patch("sensors.mqtt_publisher.mqtt")
    def test_disconnect_stops_loop(self, mock_mqtt):
        mock_client = MagicMock()
        mock_mqtt.Client.return_value = mock_client
        pub = MQTTPublisher()
        pub.connect()
        pub.disconnect()
        mock_client.loop_stop.assert_called_once()


class TestMQTTPublisherReconnect:
    """Test reconnect behavior.

    Scenario: MQTT connection survives broker restart
      Note: Full reconnection testing requires real MQTT broker.
      We test the exponential backoff configuration at least.
    """

    def test_backoff_configurations(self):
        pub = MQTTPublisher(
            backoff_base=2.0,
            backoff_max=60.0,
        )
        assert pub.backoff_base == 2.0
        assert pub.backoff_max == 60.0


class TestMQTTPublisherErrorHandling:
    """Test error handling per specs/mqtt_publishing.feature.

    Scenario: Simulator handles broker unreachable
      - Should log connection error
      - Should retry with exponential backoff
      - Should not crash
    """

    def test_connect_without_paho_returns_false(self):
        # Mock mqtt module as None
        with patch("sensors.mqtt_publisher.mqtt", None):
            pub = MQTTPublisher()
            result = pub.connect()
        assert result is False

    def test_publish_without_init_returns_false(self):
        pub = MQTTPublisher()
        result = pub.publish({"test": 1})
        assert result is False
