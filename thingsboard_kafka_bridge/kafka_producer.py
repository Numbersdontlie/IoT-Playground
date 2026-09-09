"""Kafka producer for the ThingsBoard to Kafka bridge.

Routes ThingsBoard webhook events to appropriate Kafka topics.
"""

import logging
from typing import Optional, Dict, Any

try:
    from confluent_kafka import Producer, KafkaException
except ImportError:
    Producer = None  # type: ignore
    KafkaException = Exception  # type: ignore

logger = logging.getLogger(__name__)

DEFAULT_TELEMETRY_TOPIC = "thingsboard.telemetry"
DEFAULT_ALARM_TOPIC = "thingsboard.alarm"
DEFAULT_ATTRIBUTE_TOPIC = "thingsboard.attributes"
DEFAULT_BOOTSTRAP = "localhost:9092"

DEFAULT_EVENT_ROUTES: Dict[str, str] = {
    "POST_TELEMETRY_REQUEST": DEFAULT_TELEMETRY_TOPIC,
    "ALARM": DEFAULT_ALARM_TOPIC,
    "ATTRIBUTE_UPDATE": DEFAULT_ATTRIBUTE_TOPIC,
}


class KafkaBridgeProducer:
    """Routes ThingsBoard events to Kafka topics.

    Attributes:
        EVENT_ROUTES: Mapping of event types to Kafka topics.
        telemetry_topic: Topic for telemetry events.
        alarm_topic: Topic for alarm events.
        attribute_topic: Topic for attribute update events.
        bootstrap_servers: Kafka broker addresses.
    """

    def __init__(
        self,
        telemetry_topic: str = DEFAULT_TELEMETRY_TOPIC,
        alarm_topic: str = DEFAULT_ALARM_TOPIC,
        attribute_topic: str = DEFAULT_ATTRIBUTE_TOPIC,
        bootstrap_servers: str = DEFAULT_BOOTSTRAP,
        routes: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize bridge producer.

        Args:
            telemetry_topic: Topic for telemetry events.
            alarm_topic: Topic for alarm events.
            attribute_topic: Topic for attribute updates.
            bootstrap_servers: Kafka broker connection string.
            routes: Optional custom event-to-topic routing table.
        """
        self.telemetry_topic = telemetry_topic
        self.alarm_topic = alarm_topic
        self.attribute_topic = attribute_topic
        self.bootstrap_servers = bootstrap_servers
        self._producer: Optional[Producer] = None  # type: ignore
        self._initialized = False
        self._healthy = False

        if routes:
            self.EVENT_ROUTES = routes
        else:
            self.EVENT_ROUTES = {
                "POST_TELEMETRY_REQUEST": telemetry_topic,
                "ALARM": alarm_topic,
                "ATTRIBUTE_UPDATE": attribute_topic,
            }

        self._configure_producer()

    def _configure_producer(self) -> None:
        """Configure the Kafka producer."""
        if Producer is None:
            logger.warning("confluent-kafka not installed")
            return

        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "acks": "all",
            "error_cb": self._error_callback,
        }

        self._producer = Producer(config)
        self._initialized = True
        self._healthy = True

    def publish_event(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """Publish a ThingsBoard event to the appropriate Kafka topic.

        Args:
            event_type: Type of event (e.g., "POST_TELEMETRY_REQUEST").
            event_data: Event payload dict.

        Returns:
            True if published, False otherwise.
        """
        if not self._initialized:
            logger.error("Bridge producer not initialized")
            self._healthy = False
            return False

        topic = self._resolve_topic(event_type)
        if topic is None:
            logger.warning("Unknown event type: %s", event_type)
            return False

        try:
            import json
            payload = json.dumps(event_data).encode("utf-8")
            self._producer.produce(topic=topic, value=payload)
            self._producer.poll(0)
            logger.debug("Published %s to %s", event_type, topic)
            return True
        except KafkaException as e:
            logger.error("Bridge Kafka publish failed: %s", e)
            self._healthy = False
            return False
        except Exception as e:
            logger.error("Bridge publish error: %s", e)
            self._healthy = False
            return False

    def _resolve_topic(self, event_type: str) -> Optional[str]:
        """Resolve event type to Kafka topic.

        Args:
            event_type: Event type string.

        Returns:
            Topic name or None if unknown.
        """
        return self.EVENT_ROUTES.get(event_type)

    def check_health(self) -> bool:
        """Check bridge health status.

        Returns:
            True if producer is initialized and healthy.
        """
        return self._initialized and self._healthy

    def _error_callback(self, err: KafkaException) -> None:
        """Handle Kafka errors.

        Args:
            err: KafkaException instance.
        """
        self._healthy = False
        logger.error("Bridge Kafka error: %s", err)

    @property
    def is_healthy(self) -> bool:
        """Check if producer is healthy."""
        return self._initialized and self._healthy

    @property
    def initialized(self) -> bool:
        """Check if producer is initialized."""
        return self._initialized
