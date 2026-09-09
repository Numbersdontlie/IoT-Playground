"""Sensor simulator orchestrator for industrial IoT simulation.

Manages multiple MachineState instances, publishes telemetry
via both MQTT and Kafka at configured intervals.
"""

import asyncio
import logging
import os
from typing import List

from sensors.machine_state import MachineState
from sensors.mqtt_publisher import MQTTPublisher
from sensors.kafka_publisher import KafkaPublisher

logger = logging.getLogger(__name__)

# Defaults from SDD
DEFAULT_MQTT_BROKER = "localhost"
DEFAULT_MQTT_PORT = 1884
DEFAULT_MQTT_TOPIC = "v1/devices/me/telemetry"
DEFAULT_KAFKA_BROKER = "localhost:9092"
DEFAULT_SENSOR_INTERVAL = 5
DEFAULT_MACHINE_COUNT = 10
DEFAULT_DEGRADATION_SPEED = 1


class SensorSimulator:
    """Orchestrates sensor simulation for N independent machines.

    Attributes:
        machines: List of MachineState instances.
        mqtt_publisher: Publisher for ThingsBoard MQTT.
        kafka_publisher: Publisher for Kafka streaming.
        mqtt_broker: MQTT broker address.
        mqtt_port: MQTT broker port.
        mqtt_topic: MQTT topic for telemetry.
        kafka_topic: Kafka topic for raw data.
        kafka_bootstrap: Kafka bootstrap servers.
        interval: Publish interval in seconds.
        machine_count: Number of machines to simulate.
        degradation_speed: Machine hours per real second.
        _running: Whether the simulator is active.
    """

    def __init__(
        self,
        mqtt_broker: str = DEFAULT_MQTT_BROKER,
        mqtt_port: int = DEFAULT_MQTT_PORT,
        mqtt_topic: str = DEFAULT_MQTT_TOPIC,
        kafka_bootstrap: str = DEFAULT_KAFKA_BROKER,
        kafka_topic: str = "iot.sensors.raw",
        interval: int = DEFAULT_SENSOR_INTERVAL,
        machine_count: int = DEFAULT_MACHINE_COUNT,
        degradation_speed: int = DEFAULT_DEGRADATION_SPEED,
    ) -> None:
        """Initialize simulator.

        Args:
            mqtt_broker: MQTT broker address.
            mqtt_port: MQTT broker port.
            mqtt_topic: MQTT topic for telemetry.
            kafka_bootstrap: Kafka bootstrap servers.
            kafka_topic: Kafka topic for raw data.
            interval: Seconds between sensor reads.
            machine_count: Number of simulated machines.
            degradation_speed: Machine hours per real second.
        """
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.kafka_bootstrap = kafka_bootstrap
        self.kafka_topic = kafka_topic
        self.interval = interval
        self.machine_count = machine_count
        self.degradation_speed = degradation_speed

        self.mqtt_publisher = MQTTPublisher(
            broker=mqtt_broker,
            port=mqtt_port,
            topic=mqtt_topic,
        )
        self.kafka_publisher = KafkaPublisher(
            topic=kafka_topic,
            bootstrap_servers=kafka_bootstrap,
        )

        self.machines: List[MachineState] = []
        self._running = False

    def create_machines(self) -> None:
        """Create machine state instances."""
        self.machines = [
            MachineState(machine_id=f"machine-{i+1}")
            for i in range(self.machine_count)
        ]
        logger.info("Created %d machines", len(self.machines))

    async def run(self) -> None:
        """Run the simulation loop.

        This is the main entry point. It runs indefinitely, publishing
        telemetry at configured intervals. Call stop() to end.
        """
        self.create_machines()
        self._running = True

        # Try to connect MQTT (non-blocking)
        try:
            self.mqtt_publisher.connect()
        except Exception as e:
            logger.warning("MQTT connection failed (continuing): %s", e)

        try:
            while self._running:
                await self._publish_cycle()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("Simulation cancelled")
        finally:
            self._running = False
            self.mqtt_publisher.disconnect()

    async def _publish_cycle(self) -> None:
        """Publish telemetry for all machines in one cycle."""
        for machine in self.machines:
            telemetry = machine.get_telemetry()
            machine.tick(self.degradation_speed * self.interval)

            # Publish to MQTT
            try:
                self.mqtt_publisher.publish(telemetry)
            except Exception as e:
                logger.warning("MQTT publish failed for %s: %s",
                             machine.machine_id, e)

            # Publish to Kafka
            try:
                self.kafka_publisher.publish(
                    key=machine.machine_id,
                    value=telemetry,
                )
            except Exception as e:
                logger.warning("Kafka publish failed for %s: %s",
                             machine.machine_id, e)

    def stop(self) -> None:
        """Stop the simulator."""
        self._running = False
        logger.info("Simulator stopped")

    def get_machines(self) -> List[MachineState]:
        """Get list of machine states.

        Returns:
            List of MachineState instances.
        """
        return self.machines

    def get_config(self) -> dict:
        """Get simulator configuration.

        Returns:
            Dict of configuration parameters.
        """
        return {
            "mqtt_broker": self.mqtt_broker,
            "mqtt_port": self.mqtt_port,
            "mqtt_topic": self.mqtt_topic,
            "kafka_bootstrap": self.kafka_bootstrap,
            "kafka_topic": self.kafka_topic,
            "interval": self.interval,
            "machine_count": self.machine_count,
            "degradation_speed": self.degradation_speed,
        }
