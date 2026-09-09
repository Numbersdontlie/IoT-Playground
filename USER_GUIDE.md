# IoT Playground — User Guide

## What Is This Project?

An end-to-end industrial IoT simulation platform that:

1. **Simulates** N industrial machines with realistic sensor degradation (temperature, vibration, pressure, humidity)
2. **Publishes** telemetry via MQTT (to ThingsBoard) and Kafka
3. **Routes** ThingsBoard events through a Kafka bridge for downstream consumers
4. **Tracks** machine health over time with configurable degradation models

---

## Prerequisites

### System Packages (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y librdkafka-dev gcc g++
```

### Python

```bash
# Requires Python 3.12+
python3 --version

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # reload
```

---

## Installation

### 1. Install Dependencies

```bash
cd IoT-Playground

# Create virtual environment with uv
uv venv .venv

# Activate it
source .venv/bin/activate

# Install all project dependencies
uv pip install -r sensors/requirements.txt -r thingsboard_kafka_bridge/requirements.txt
```

### 2. Start Infrastructure (Docker)

```bash
# Start all services in background
make up

# Wait ~2 minutes for PostgreSQL and ThingsBoard to fully initialize

# Verify services are running
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### 3. Verify Kafka Client

```bash
# Check if confluent-kafka is installed
python -c "from confluent_kafka import Producer; print('OK')"
```

---

## Docker Services Reference

| Service | Port(s) | URL | Purpose |
|---------|---------|-----|---------|
| **ThingsBoard** | 8080 | http://localhost:8080 | Device management dashboard |
| **pgAdmin** | 5050 | http://localhost:5050 | PostgreSQL admin interface |
| **Kafka UI** | 8085 | http://localhost:8085 | Browse Kafka topics & messages |
| **PostgreSQL** | 5432 | — | ThingsBoard database |

### ThingsBoard Default Login

```
Email:    thingadmin@admin.com
Password: thingadmin
```

### pgAdmin Default Login

```
Email:    luisperez@admin.com
Password: master
```

---

## Usage

### Option A: Docker Compose (Recommended)

All services start together. Just run the simulator:

```bash
make up
make sensor-run          # Runs simulator locally, publishes to Docker Kafka/MQTT
```

### Option B: Standalone (No Docker)

Run Kafka and MQTT yourself, then run simulator and bridge:

```bash
# 1. Start Kafka (you manage this separately)
# Your Kafka must be reachable at localhost:9092

# 2. Start simulator
make sensor-run

# 3. In another terminal, start bridge
make bridge-run
```

### Option C: Full Docker with Local Simulator

```bash
make up                     # Start Docker services
source .venv/bin/activate   # Activate venv
SENSOR_INTERVAL=2 MACHINE_COUNT=20 make sensor-run  # Run with custom config
```

---

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BROKER` | `localhost:9092` | Kafka bootstrap server |
| `ZOOKEEPER_HOST` | `zookeeper:2181` | ZooKeeper connect string |
| `MQTT_BROKER` | `localhost` | MQTT broker address |
| `MQTT_PORT` | `1884` | MQTT broker port |
| `MQTT_TOPIC` | `v1/devices/me/telemetry` | ThingsBoard MQTT topic |
| `SENSOR_INTERVAL` | `5` | Seconds between sensor readings |
| `MACHINE_COUNT` | `10` | Number of simulated machines |
| `DEGRADATION_SPEED` | `1` | Machine hours per real second |
| `BRIDGE_PORT` | `8086` | Bridge webhook server port |
| `TOPIC_RAW` | `iot.sensors.raw` | Kafka topic for raw sensor data |
| `TOPIC_TELEMETRY` | `thingsboard.telemetry` | Kafka topic for ThingsBoard telemetry |
| `TOPIC_ALARM` | `thingsboard.alarm` | Kafka topic for alarm events |

### Running With Custom Config

```bash
# Override via command line
MACHINE_COUNT=5 SENSOR_INTERVAL=2 make sensor-run

# Or edit .env and reload Docker
make up
```

---

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make up` | Start all Docker services |
| `make down` | Stop Docker containers |
| `make sensor-run` | Run sensor simulator locally |
| `make bridge-run` | Run Kafka bridge locally |
| `make clean` | Stop and remove all containers + images |
| `make prune` | Full system cleanup + free disk space |

---

## Kafka Topics

| Topic | Producer | Purpose |
|-------|----------|---------|
| `iot.sensors.raw` | Simulator | Raw sensor readings from machines |
| `thingsboard.telemetry` | Bridge | Telemetry from ThingsBoard devices |
| `thingsboard.alarm` | Bridge | Alarm events from ThingsBoard |

### Viewing Messages in Kafka UI

1. Open http://localhost:8085
2. Click "Explore Data" → "Messages"
3. Select topic and read messages

---

## Testing

```bash
source .venv/bin/activate

# Run all tests
python -m pytest sensors/tests/ thingsboard_kafka_bridge/tests/ -v

# Run specific test file
python -m pytest sensors/tests/test_sensor_simulator.py -v

# Run with coverage
uv pip install coverage
coverage run -m pytest sensors/tests/ thingsboard_kafka_bridge/tests/
coverage report
```

### Test Summary

| Category | Tests | Status |
|----------|-------|--------|
| Degradation models | ~30 | ✅ Passing |
| Machine state | ~15 | ✅ Passing |
| MQTT publisher | ~10 | ✅ Passing |
| Kafka publisher | ~12 | ✅ Passing (if confluent-kafka installed) |
| Sensor simulator | ~20 | ✅ Passing |
| Integration | ~13 | ✅ Passing |
| Kafka bridge producer | ~20 | ✅ Passing (if confluent-kafka installed) |
| Webhook server | ~15 | ✅ Passing |
| Routing | ~10 | ✅ Passing |
| **Total** | **196** | **196 passed, 2 skipped** |

---

## Architecture Overview

```
┌──────────────┐    MQTT     ┌───────────────┐
│  Simulator   │ ──────────► │   ThingsBoard │
│ (Kafka+MQTT) │             │   (IoT Mgmt)  │
└──────────────┘             └───────┬───────┘
                                     │ Webhook
                                     ▼
                              ┌───────────────┐     Kafka     ┌──────────┐
                              │  Kafka Bridge  │ ──────────► │  Any     │
                              │ (Flask + Kafka)│  topics     │ Consumer │
                              └───────────────┘             └──────────┘
```

### Data Flow

1. **Simulator** creates N machines with sensor degradation models
2. Each machine publishes readings via **MQTT** (to ThingsBoard) and **Kafka** (raw topic)
3. **ThingsBoard** receives telemetry and sends webhook events
4. **Kafka Bridge** receives webhooks and publishes to Kafka topics
5. **Downstream consumers** read from Kafka topics

---

## Troubleshooting

### confluent-kafka Import Error

```
ModuleNotFoundError: No module named 'confluent_kafka'
```

**Fix:**

```bash
sudo apt install -y librdkafka-dev
uv pip install confluent-kafka
```

### Kafka Connection Refused

```
kafka: Connection refused
```

**Fix:**

```bash
# Check if Kafka is running
docker ps | grep kafka

# Restart Kafka
docker restart kafka
```

### ThingsBoard Not Ready

```
Connection to ThingsBoard MQTT failed
```

**Fix:**

```bash
# Wait for ThingsBoard to fully initialize
docker logs thingsboard | grep "Started ThingsBoard"

# Re-run after 2 more minutes
make sensor-run
```

### Docker Port Conflicts

```
Port 5432 is already in use
```

**Fix:** Edit `.env` or `docker-compose.yml` to use different host ports.

---

## Quick Reference Cheat Sheet

```bash
# One-command start
make up && make sensor-run

# Check everything
docker ps && make -n sensor-run && make -n bridge-run

# Reset everything
make clean && make up

# Run tests
python -m pytest --tb=short -q
```
