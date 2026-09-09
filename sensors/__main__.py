"""Entry point for running sensor simulator directly."""
import asyncio
import logging
import os

from sensors.sensor_simulator import SensorSimulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def main():
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
