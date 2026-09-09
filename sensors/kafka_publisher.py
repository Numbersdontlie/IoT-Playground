"""Kafka publisher for streaming sensor data.

Uses confluent-kafka Producer with acks="all" for durability
and murmur2 partitioning by machine_id.
"""

import json
import logging
from typing import Optional

try:
    from confluent_kafka import Producer, KafkaException
except ImportError:
    Producer = None  # type: ignore
    KafkaException = Exception  # type: ignore

logger = logging.getLogger(__name__)

DEFAULT_TOPIC = "iot.sensors.raw"
DEFAULT_BOOTSTRAP = "localhost:9092"


class KafkaPublisher:
    """Publishes sensor telemetry to Kafka.

    Attributes:
        topic: Kafka topic to publish to.
        bootstrap_servers: Kafka broker addresses.
        acks: Delivery acknowledgment level.
        partitioner: Key partitioner algorithm.
    """

    def __init__(
        self,
        topic: str = DEFAULT_TOPIC,
        bootstrap_servers: str = DEFAULT_BOOTSTRAP,
        acks: str = "all",
        partitioner: str = "murmur2",
    ) -> None:
        """Initialize Kafka publisher.

        Args:
            topic: Target Kafka topic.
            bootstrap_servers: Kafka broker connection string.
            acks: Acknowledgment level ("all", "1", "0").
            partitioner: Partitioner for key-based routing.
        """
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.acks = acks
        self._producer: Optional[Producer] = None  # type: ignore
        self._initialized = False
        self._errors: list = []

        self._configure_producer(acks, partitioner)

    def _configure_producer(self, acks: str, partitioner: str) -> None:
        """Configure and initialize the Kafka producer.

        Args:
            acks: Acknowledgment level.
            partitioner: Partitioner name.
        """
        if Producer is None:
            logger.warning("confluent-kafka not installed")
            return

        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "acks": acks,
            "partitioner": partitioner,
            "error_cb": self._error_callback,
        }

        self._producer = Producer(config)
        self._initialized = True

    def publish(self, key: str, value: dict) -> bool:
        """Publish a single telemetry message to Kafka.

        Args:
            key: Machine ID (used for partitioning).
            value: Telemetry data dict.

        Returns:
            True if successfully enqueued, False otherwise.
        """
        if not self._initialized or self._producer is None:
            logger.error("Kafka producer not initialized")
            return False

        try:
            payload = json.dumps(value).encode("utf-8")
            self._producer.produce(
                topic=self.topic,
                key=key.encode("utf-8"),
                value=payload,
            )
            self._producer.poll(0)
            return True
        except KafkaException as e:
            logger.error("Kafka produce failed: %s", e)
            return False
        except Exception as e:
            logger.error("Kafka publish error: %s", e)
            return False

    def flush(self, timeout: float = 5.0) -> int:
        """Flush pending messages.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Number of messages still in queue.
        """
        if self._producer is None:
            return 0
        return self._producer.flush(timeout)

    @property
    def get_topic(self) -> str:
        """Return the configured topic."""
        return self.topic

    @property
    def get_acks(self) -> str:
        """Return the acknowledgment level."""
        return self.acks

    @property
    def initialized(self) -> bool:
        """Check if producer is initialized."""
        return self._initialized

    def _error_callback(self, err: KafkaException) -> None:
        """Handle Kafka errors.

        Args:
            err: KafkaException instance.
        """
        self._errors.append(str(err))
        logger.error("Kafka error: %s", err)

    def get_errors(self) -> list:
        """Return list of errors encountered.

        Returns:
            List of error message strings.
        """
        return self._errors.copy()

    def flush(self, timeout: float = 5.0) -> int:
        """Flush all pending messages to Kafka.

        Call this before shutdown to prevent message loss.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Number of messages still in queue after flush attempt.
        """
        if self._producer is None:
            return 0
        return self._producer.flush(timeout)
