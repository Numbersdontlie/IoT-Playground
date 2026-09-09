"""Sensor simulator orchestrator for industrial IoT simulation.

Manages multiple MachineState instances, publishes telemetry
via both MQTT and Kafka at configured intervals.
"""

import asyncio
import logging
import os
import json
import hashlib
from typing import List, Optional

from sensors.machine_state import MachineState
from sensors.mqtt_publisher import MQTTPublisher
from sensors.kafka_publisher import KafkaPublisher

logger = logging.getLogger(__name__)

DEFAULT_MQTT_BROKER = "localhost"
DEFAULT_MQTT_PORT = 1884
DEFAULT_MQTT_TOPIC = "v1/devices/me/telemetry"
DEFAULT_KAFKA_BROKER = "localhost:9092"
DEFAULT_SENSOR_INTERVAL = 5
DEFAULT_MACHINE_COUNT = 10
DEFAULT_DEGRADATION_SPEED = 1
DEFAULT_STATE_FILE = "machine_state.json"


class SensorSimulator:
    """Orchestrates sensor simulation for N independent machines.

    Attributes:
        machines: List of MachineState instances.
        mqtt_publishers: Per-machine MQTT publishers.
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
        state_file: Optional[str] = None,
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
            state_file: Path to persist machine state between runs.
        """
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.kafka_bootstrap = kafka_bootstrap
        self.kafka_topic = kafka_topic
        self.interval = interval
        self.machine_count = machine_count
        self.degradation_speed = degradation_speed
        self.state_file = state_file or DEFAULT_STATE_FILE

        self.mqtt_publishers: List[MQTTPublisher] = []
        self.kafka_publisher = KafkaPublisher(
            topic=kafka_topic,
            bootstrap_servers=kafka_bootstrap,
        )

        self.machines: List[MachineState] = []
        self._running = False

    def create_machines(self) -> None:
        """Create machine state instances with per-machine MQTT publishers.

        Each machine gets its own MQTT client with a unique token.
        Tokens are generated deterministically from machine_id.
        """
        self.machines = []
        self.mqtt_publishers = []

        for i in range(self.machine_count):
            machine_id = f"machine-{i+1}"
            token = self._generate_token(machine_id)
            machine = MachineState(machine_id=machine_id)

            publisher = MQTTPublisher(
                broker=self.mqtt_broker,
                port=self.mqtt_port,
                topic=self.mqtt_topic,
                token=token,
            )
            self.mqtt_publishers.append(publisher)
            self.machines.append(machine)

        logger.info("Created %d machines", len(self.machines))

    @staticmethod
    def _generate_token(machine_id: str) -> str:
        """Generate a deterministic device token from machine_id.

        Args:
            machine_id: Machine identifier.

        Returns:
            Access token string for MQTT authentication.
        """
        return hashlib.sha256(machine_id.encode()).hexdigest()[:32]

    async def run(self) -> None:
        """Run the simulation loop.

        This is the main entry point. It runs indefinitely, publishing
        telemetry at configured intervals. Call stop() to end.
        """
        self._load_or_create_machines()
        self._running = True

        for publisher in self.mqtt_publishers:
            try:
                publisher.connect()
            except Exception as e:
                logger.warning("MQTT connection failed: %s", e)

        try:
            while self._running:
                await self._publish_cycle()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("Simulation cancelled")
        finally:
            self._running = False
            self._save_state()
            for publisher in self.mqtt_publishers:
                publisher.disconnect()
            self.kafka_publisher.flush(timeout=5.0)

    def _load_or_create_machines(self) -> None:
        """Load existing machine state or create new machines."""
        if os.path.exists(self.state_file):
            try:
                self._load_state()
            except (json.JSONDecodeError, KeyError) as e:
                logger.error("Failed to load state: %s", e)
                self.create_machines()
        else:
            self.create_machines()

    def _load_state(self) -> None:
        """Load machine state from file."""
        with open(self.state_file, "r") as f:
            data = json.load(f)

        self.machines = []
        self.mqtt_publishers = []

        for mdata in data["machines"]:
            machine_id = mdata["machine_id"]
            machine = MachineState(machine_id=machine_id)
            machine.age_hours = mdata.get("age_hours", 0.0)
            machine.health_pct = mdata.get("health_pct", 100.0)
            machine.last_pressure_value = mdata.get(
                "last_pressure_value", 4.0
            )

            token = self._generate_token(machine_id)
            publisher = MQTTPublisher(
                broker=self.mqtt_broker,
                port=self.mqtt_port,
                topic=self.mqtt_topic,
                token=token,
            )
            self.mqtt_publishers.append(publisher)
            self.machines.append(machine)

        logger.info(
            "Loaded %d machines from %s", len(self.machines), self.state_file
        )

    def _save_state(self) -> None:
        """Save machine state to file."""
        data = {
            "machines": [
                {
                    "machine_id": m.machine_id,
                    "age_hours": m.age_hours,
                    "health_pct": m.health_pct,
                    "last_pressure_value": m.last_pressure_value,
                }
                for m in self.machines
            ]
        }

        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("Saved state for %d machines", len(self.machines))

    async def _publish_cycle(self) -> None:
        """Publish telemetry for all machines in one cycle."""
        tasks = []
        for i, machine in enumerate(self.machines):
            telemetry = machine.get_telemetry()
            machine.tick(self.degradation_speed * self.interval)

            kafka_task = asyncio.get_event_loop().run_in_executor(
                None,
                self._publish_kafka,
                machine.machine_id,
                telemetry,
            )
            tasks.append(kafka_task)

            mqtt_task = asyncio.get_event_loop().run_in_executor(
                None,
                self._publish_mqtt,
                i,
                telemetry,
            )
            tasks.append(mqtt_task)

        await asyncio.gather(*tasks, return_exceptions=True)

    def _publish_kafka(self, key: str, value: dict) -> None:
        """Publish to Kafka (run in executor to avoid blocking)."""
        try:
            self.kafka_publisher.publish(key=key, value=value)
        except Exception as e:
            logger.warning("Kafka publish failed for %s: %s", key, e)

    def _publish_mqtt(self, publisher_idx: int, payload: dict) -> None:
        """Publish to MQTT (run in executor to avoid blocking)."""
        try:
            publisher = self.mqtt_publishers[publisher_idx]
            publisher.publish(payload)
        except Exception as e:
            logger.warning("MQTT publish failed: %s", e)

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
            "state_file": self.state_file,
        }


def main() -> None:
    """Run the simulator with env var configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    broker = os.getenv("MQTT_BROKER", "localhost")
    port = int(os.getenv("MQTT_PORT", "1884"))
    kafka_broker = os.getenv("KAFKA_BROKER", "localhost:9092")
    interval = int(os.getenv("SENSOR_INTERVAL", "5"))
    count = int(os.getenv("MACHINE_COUNT", "10"))
    speed = int(os.getenv("DEGRADATION_SPEED", "1"))

    sim = SensorSimulator(
        mqtt_broker=broker,
        mqtt_port=port,
        kafka_bootstrap=kafka_broker,
        interval=interval,
        machine_count=count,
        degradation_speed=speed,
    )
    asyncio.run(sim.run())


if __name__ == "__main__":
    main()
