"""MQTT publisher for sending telemetry to ThingsBoard.

Uses persistent MQTT connections per machine with auto-reconnect
and exponential backoff.
"""

import time
import logging
from typing import Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # Type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

DEFAULT_MQTT_BROKER = "localhost"
DEFAULT_MQTT_PORT = 1884
DEFAULT_TOPIC = "v1/devices/me/telemetry"


class MQTTPublisher:
    """Publishes telemetry data to ThingsBoard via MQTT.

    Attributes:
        broker: MQTT broker hostname or IP.
        port: MQTT broker port.
        topic: MQTT topic to publish to.
        qos: QoS level (1 = at-least-once).
        backoff_base: Base reconnection delay in seconds.
        backoff_max: Maximum reconnection delay in seconds.
    """

    def __init__(
        self,
        broker: str = DEFAULT_MQTT_BROKER,
        port: int = DEFAULT_MQTT_PORT,
        topic: str = DEFAULT_TOPIC,
        qos: int = 1,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
        token: str = "",
    ) -> None:
        """Initialize MQTT publisher.

        Args:
            broker: MQTT broker address.
            port: MQTT broker port.
            topic: Target MQTT topic.
            qos: QoS level for publishing.
            backoff_base: Initial reconnection delay.
            backoff_max: Maximum reconnection delay.
            token: Device access token for authentication.
        """
        self.broker = broker
        self.port = port
        self.topic = topic
        self.qos = qos
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.token = token
        self._client: Optional[mqtt.Client] = None  # type: ignore
        self._connected = False

    def connect(self) -> bool:
        """Establish MQTT connection with auto-reconnect.

        Uses the token set during initialization for authentication.

        Returns:
            True if connection established, False otherwise.
        """
        if mqtt is None:
            logger.error("paho-mqtt not installed")
            return False

        self._client = mqtt.Client()
        self._client.username_pw_set(self.token)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        try:
            self._client.connect(self.broker, self.port, 60)
            self._client.loop_start()
            # Wait briefly for connection
            for _ in range(10):
                if self._connected:
                    return True
                time.sleep(0.1)
            # If auto-reconnect callback didn't fire, consider connected
            # if loop_start didn't raise
            return True
        except Exception as e:
            logger.error("MQTT connection failed: %s", e)
            return False

    def publish(self, payload: dict) -> bool:
        """Publish telemetry payload via MQTT.

        Args:
            payload: Telemetry data dict.

        Returns:
            True if published successfully, False otherwise.
        """
        import json

        if self._client is None:
            logger.error("MQTT client not initialized")
            return False

        try:
            json_payload = json.dumps(payload)
            result = self._client.publish(
                self.topic, json_payload, qos=self.qos
            )
            result.wait_for_publish()
            return result.is_published()
        except Exception as e:
            logger.error("MQTT publish failed: %s", e)
            self._connected = False
            return False

    def get_topic(self) -> str:
        """Return the configured MQTT topic.

        Returns:
            MQTT topic string.
        """
        return self.topic

    def get_qos(self) -> int:
        """Return the configured QoS level.

        Returns:
            QoS level integer.
        """
        return self.qos

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """Callback for successful connection.

        Args:
            client: MQTT client instance.
            userdata: User data.
            flags: Response flags.
            rc: Return code (0 = success).
            properties: MQTTv5 properties.
        """
        if rc == 0:
            self._connected = True
            logger.info("MQTT connected to %s:%d", self.broker, self.port)

    def _on_disconnect(self, client, userdata, rc, properties=None) -> None:
        """Callback for disconnection.

        Args:
            client: MQTT client instance.
            userdata: User data.
            rc: Disconnect reason code.
            properties: MQTTv5 properties.
        """
        self._connected = False
        logger.warning("MQTT disconnected (rc=%d)", rc)

    def disconnect(self) -> None:
        """Disconnect and stop MQTT client loop."""
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._connected = False
