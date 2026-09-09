# AGENTS.md — AI Agent Guidelines for IoT Playground

## Project Structure

```
IoT-Playground/
├── docker-compose.yml          # Docker orchestration
├── Makefile                    # Build/run commands
├── .env                        # Environment variables
├── SDD.md                      # Software Design Document
├── ARCHITECTURE.md             # System architecture
├── sensors/                    # Sensor simulator package
│   ├── __init__.py
│   ├── requirements.txt
│   ├── sensor_simulator.py
│   ├── mqtt_publisher.py
│   ├── kafka_publisher.py
│   ├── degradation_models.py
│   ├── machine_state.py
│   └── tests/
│       ├── test_degradation_models.py
│       ├── test_machine_state.py
│       ├── test_kafka_publisher.py
│       ├── test_mqtt_publisher.py
│       └── test_sensor_simulator.py
├── thingsboard_kafka_bridge/   # ThingsBoard → Kafka bridge
│   ├── __init__.py
│   ├── requirements.txt
│   ├── webhook_server.py
│   ├── kafka_producer.py
│   └── tests/
│       ├── test_webhook_server.py
│       ├── test_kafka_producer.py
│       └── test_routing.py
└── specs/                      # Gherkin test specifications
    └── *.feature
```

## Running the Project

```bash
# Start all infrastructure
make up

# Run sensor simulator
make sensor-run

# Run Kafka bridge standalone
make bridge-run

# Stop and clean
make clean
```

## Configuration

All configuration via `.env` file:

```env
# Kafka
KAFKA_BROKER=localhost:9092
ZOOKEEPER_HOST=zookeeper:2181
BOOTSTRAP_SERVERS=kafka:29092

# MQTT
MQTT_BROKER=localhost
MQTT_PORT=1884
MQTT_TOPIC=v1/devices/me/telemetry

# Simulator
SENSOR_INTERVAL=5
MACHINE_COUNT=10
DEGRADATION_SPEED=1

# Kafka Topics
TOPIC_RAW=iot.sensors.raw
TOPIC_TELEMETRY=thingsboard.telemetry
TOPIC_ALARM=thingsboard.alarm

# Bridge
BRIDGE_PORT=8086
```

## Code Conventions

### Python

- Python 3.10+ (use `asyncio` for concurrent machine simulation)
- Type hints required on all public functions
- Docstrings using Google style
- 88 char line limit (Black formatter)
- No external logging library — use `logging` module with JSON format

### Python Imports

```python
# Standard library first
import asyncio
import json
import logging

# Third-party
import paho.mqtt.client as mqtt
from confluent_kafka import Producer

# Local
from sensors.degradation_models import temperature, vibration
```

### Error Handling

```python
try:
    producer.produce(topic, key=key, value=json.dumps(payload).encode())
except KafkaException as e:
    logger.error(f"Kafka produce failed: {e}")
    # Continue simulation (fail-fast for Kafka is acceptable)
```

### Degradation Model Guidelines

- Each model is a pure function: `f(age_hours) -> float`
- Add noise using `random.gauss(0, sigma)` — never seed globally
- Models should never mutate state
- Document the physical meaning of each parameter

### Kafka Publishing

- Use `acks="all"` for durability
- Set `partitioner="murmur2"` for consistent machine_id → partition mapping
- Keys must be `machine_id` strings for hash-partitioning

### MQTT Publishing

- Use QoS 1 (at-least-once delivery)
- Handle disconnects with exponential backoff
- Never block the main async loop on network I/O

## ThingsBoard Integration

### Device Provisioning

The simulator must create devices in ThingsBoard:
1. Register device via ThingsBoard REST API on first run
2. Store device access token in `.env` or device config
3. Use token as MQTT username for authentication

### Rule Engine Setup

After starting ThingsBoard, configure the webhook:
1. Rule Chains → Create chain
2. Function node: filter `POST_TELEMETRY_REQUEST` and `ALARM`
3. Webhook node: `http://localhost:8086/events` (dev) or `http://thingsboard-kafka-bridge:8086/events` (Docker)

## Kafka Topics

| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `iot.sensors.raw` | Simulator | Any | Raw sensor readings |
| `thingsboard.telemetry` | Bridge | Any | ThingsBoard device telemetry |
| `thingsboard.alarm` | Bridge | Any | ThingsBoard alarm events |

## Testing

Run tests with pytest:
```bash
# Run all tests
python -m pytest sensors/tests/ thingsboard_kafka_bridge/tests/ -v

# Run specific package
python -m pytest sensors/tests/ -v
python -m pytest thingsboard_kafka_bridge/tests/ -v
```

Test structure:
```
sensors/tests/
├── test_degradation_models.py     # Sensor model ranges, alarms, health
├── test_machine_state.py          # Machine creation, telemetry, aging
├── test_kafka_publisher.py        # Publish, partitioning, error handling
├── test_mqtt_publisher.py         # MQTT connection, publish, reconnect
└── test_sensor_simulator.py       # Simulator orchestration, config

thingsboard_kafka_bridge/tests/
├── test_webhook_server.py         # Flask endpoints, event handling
├── test_kafka_producer.py         # Event routing, health checks
└── test_routing.py                # Event type mapping, validation
```

## Kafka UI Access

- URL: `http://localhost:8085`
- No auth required (dev mode)
- View topics, messages, consumer groups
