# Software Design Document — IoT Playground

## 1. System Overview

An industrial IoT simulation platform featuring:
- **10 independent simulated machines**, each with realistic degradation profiles
- **Kafka streaming** for raw sensor data and ThingsBoard event forwarding
- **ThingsBoard** MQTT ingestion, rule engine, visualization, and alarm management
- **PostgreSQL** persistent storage (via ThingsBoard)

---

## 2. Component Architecture

### 2.1 Sensor Simulator (`sensors/`)

```
sensors/
├── __init__.py
├── requirements.txt
├── sensor_simulator.py        ← Main entry point (asyncio orchestrator)
├── mqtt_publisher.py           ← Paho MQTT client → ThingsBoard
├── kafka_publisher.py          ← Confluent Kafka client → Kafka topics
├── degradation_models.py       ← Wear/tear mathematical models
└── machine_state.py            ← Per-machine state tracking
```

#### Responsibilities

| Module | Responsibility |
|--------|---------------|
| `sensor_simulator.py` | Spawns N `MachineState` instances; runs async event loop; publishes at configured intervals |
| `mqtt_publisher.py` | Connects to ThingsBoard MQTT broker; publishes to `v1/devices/me/telemetry`; handles reconnection |
| `kafka_publisher.py` | Initializes `KafkaProducer`; publishes to topic per machine; serializes JSON |
| `degradation_models.py` | Pure math functions returning sensor values given machine age + noise |
| `machine_state.py` | Encapsulates `age_hours`, `health_pct`, `machine_id`; delegates to degradation models |

#### Class: `MachineState`

```python
class MachineState:
    machine_id: str          # "machine-1" through "machine-10"
    age_hours: float         # Monotonically increasing, step = DEGRADATION_SPEED * interval
    health_pct: float        # Starts at 100.0, declines with wear
    
    def get_telemetry(self) -> dict
    def get_alarm(self) -> Optional[dict]
    def tick(self) -> None
```

#### Class: `SensorSimulator`

```python
class SensorSimulator:
    machines: list[MachineState]
    mqtt_publisher: MqtPublisher
    kafka_publisher: KafkaPublisher
    config: Config
    
    def run(self) -> None      # async, non-blocking
    def stop(self) -> None
```

---

### 2.2 MQTT Publisher

- **Library**: `paho-mqtt` v2.x
- **Broker**: ThingsBoard on port `1884`
- **Topic pattern**: `v1/devices/me/telemetry` (ThingsBoard default ingestion)
- **QoS**: 1 (at least once)
- **Client Design**: Persistent connection per machine with auto-reconnect
  - Each `MachineState` maintains its own MQTT client instance
  - Exponential backoff on reconnection: 1s, 2s, 4s, 8s, max 30s
  - Single connection reuses across all publishes for a machine
  - Serializes telemetry as JSON with millisecond timestamp

#### Telemetry Format

All telemetry uses the same flat schema for both MQTT and Kafka:

```json
{
  "Temperature": 67.42,
  "Vibration": 12.7,
  "Pressure": 4.23,
  "RPM": 1420.5,
  "Humidity": 58.1,
  "MachineHealth": 87.3,
  "timestamp": 1699999999123,
  "machine_id": "machine-3",
  "alarms": []
}
```

**Field definitions:**

| Field | Type | Description |
|-------|------|-------------|
| `Temperature` | number | Current temperature in °C |
| `Vibration` | number | Vibration amplitude in mm/s |
| `Pressure` | number | System pressure in bar |
| `RPM` | number | Motor speed in revolutions per minute |
| `Humidity` | number | Ambient humidity in %RH |
| `MachineHealth` | number | Per-machine health score (0–100) |
| `timestamp` | number | Millisecond Unix epoch |
| `machine_id` | string | Machine identifier (`machine-1`...`machine-N`) |
| `alarms` | array of strings | List of alarm names if thresholds breached |

---

### 2.3 Kafka Publisher

- **Library**: `confluent-kafka` v2.x
- **Bootstrap servers**: Configured via `KAFKA_BROKER` env var
- **Topic**: Single topic `iot.sensors.raw` for all machines
- **Serializer**: JSON (`json.dumps`) — same schema as MQTT payload
- **acks**: `"all"` for durability
- **Key**: `machine_id` string (hash-partitioned)
- **Behavior**:
  - Initializes once, reuses producer for all machines
  - Async-compatible via `producer.poll()` in event loop
  - Error callback for broker connectivity issues

#### Topic Convention

| Topic | Content | Key | Partition Strategy |
|-------|---------|-----|-------------------|
| `iot.sensors.raw` | All raw sensor readings | `machine_id` | Murmur2 hash of key — same machine always goes to same partition |

---

### 2.4 Degradation Models (`degradation_models.py`)

All models accept `(age_hours: float) -> float` and return a sensor reading.

#### 2.4.1 Temperature Model

```python
def temperature(age_hours: float) -> float:
    base = 45.0                    # Normal operating temp
    drift = 0.002 * age_hours      # Gradual thermal drift (+0.2°C per 100h)
    oscillation = 8.0 * sin(2π * age_hours / 24)  # 24h cycle
    noise = normalvariate(0, 1.5)
    return base + drift + oscillation + noise
```

#### 2.4.2 Vibration Model (Bearing Wear)

```python
def vibration(age_hours: float) -> float:
    initial = 2.5                  # mm/s, new bearing
    wear = 0.03 * sqrt(age_hours)  # Power-law wear growth
    noise = max(0, random.gauss(0, 0.5))
    spike = poisson_spike(age_hours)  # Random shock events
    return initial + wear + noise + spike
```

#### 2.4.3 Pressure Model (Random Walk with Spikes)

**Note:** This is the only stateful model. State is maintained in `MachineState.last_pressure_value` and passed to the model. All other models are pure functions.

```python
def pressure(age_hours: float, last_value: float) -> float:
    drift = random.gauss(0, 0.05)  # Random walk step
    leak = random.exponential(2.0) if random.random() < 0.001 else 0  # Rare leak events
    return last_value + drift - leak
```

**Usage pattern in `MachineState`:**
```python
class MachineState:
    last_pressure_value: float = 4.0  # Stored state, initialized on creation
    
    def get_telemetry(self) -> dict:
        pressure_value = pressure(self.age_hours, self.last_pressure_value)
        self.last_pressure_value = pressure_value
        return {...}
```

#### 2.4.4 RPM Model (Motor Degradation)

```python
def rpm(age_hours: float) -> float:
    nominal = 1500                 # rev/min, new motor
    degradation = 0.05 * age_hours # Slow decline
    variance_increase = 1 + 0.001 * age_hours  # Wobbling increases over time
    noise = normalvariate(0, 15) * variance_increase
    return nominal - degradation + noise
```

#### 2.4.5 Humidity Model (Sensor Drift)

```python
def humidity(age_hours: float) -> float:
    ambient = 50.0                 # %RH, baseline
    calibration_drift = 0.005 * age_hours  # Sensor calibration loses accuracy
    periodic = 10 * sin(2π * age_hours / 24)  # Daily humidity cycle
    noise = normalvariate(0, 1.0)
    return ambient + calibration_drift + periodic + noise
```

#### 2.4.6 Health Score Calculation

**Per-sensor health formula:**

Each sensor contributes a health percentage based on how far its reading is from the warning threshold, scaled relative to the gap between warning and critical:

```python
def sensor_health(sensor_value: float, warning_threshold: float, critical_threshold: float) -> float:
    """
    Returns health 100 (safe) → 0 (critical).
    - Value at or below warning:  100
    - Value at critical:          0
    - Linear interpolation between warning and critical.
    """
    if sensor_value <= warning_threshold:
        return 100.0
    elif sensor_value >= critical_threshold:
        return 0.0
    else:
        ratio = (sensor_value - warning_threshold) / (critical_threshold - warning_threshold)
        return max(0.0, 100.0 - ratio * 100.0)
```

**Aggregate machine health:**

```python
def calculate_machine_health(machine: MachineState) -> float:
    """Weighted average of per-sensor health scores."""
    weights = {"Vibration": 0.35, "Temperature": 0.25, "RPM": 0.2, "Pressure": 0.15, "Humidity": 0.05}
    score = 0.0
    for sensor_name, weight in weights.items():
        value = get_sensor_value(machine, sensor_name)
        w, c = get_alarm_thresholds(sensor_name)  # warning, critical
        score += sensor_health(value, w, c) * weight
    return round(score, 1)
```

**Aggregate system health** (across all machines): average of all machine health scores.

#### 2.4.7 Alarm Thresholds

| Sensor | Warning Threshold | Critical Threshold |
|--------|-------------------|-------------------|
| Temperature | > 75°C | > 90°C |
| Vibration | > 15 mm/s | > 25 mm/s |
| Pressure | < 1.5 bar | < 1.0 bar |
| RPM | > 2200 or < 800 | > 2500 or < 500 |
| Humidity | > 80% or < 20% | > 90% or < 10% |

#### Alarm Origin and Flow

Alarms originate **in the simulator** and are carried through the pipeline:

1. **Simulator detects** threshold breach by comparing sensor values against thresholds defined in §2.4.7
2. **Simulator includes** alarm names in the `alarms` array field of the telemetry payload
3. **Simulator publishes** payload via MQTT to ThingsBoard
4. **ThingsBoard stores** telemetry including the `alarms` array
5. **ThingsBoard Rule Engine** inspects the `alarms` array and triggers alarm entities in ThingsBoard
6. **Webhook** forwards the event to Kafka Bridge → `thingsboard.alarm` topic

**Alarm entity schema** (created by ThingsBoard rule engine):

```json
{
  "alarm_type": "HighTemperature",
  "severity": "CRITICAL",
  "originator": "machine-3",
  "start_ts": 1699999999123,
  "end_ts": null,
  "cleared": false,
  "details": {
    "sensor": "Temperature",
    "value": 92.5,
    "threshold": 90
  }
}
```

**Alarm severity mapping:**

| Breach | Severity |
|--------|----------|
| Warning threshold exceeded | `WARNING` |
| Critical threshold exceeded | `CRITICAL` |

---

### 2.5 Kafka Bridge (`thingsboard-kafka-bridge/`)

```
thingsboard-kafka-bridge/
├── __init__.py
├── requirements.txt
├── webhook_server.py         ← Flask/FastAPI HTTP server
└── kafka_producer.py         ← Kafka producer singleton
```

#### Responsibilities

| Module | Responsibility |
|--------|---------------|
| `webhook_server.py` | Exposes `POST /events`; validates payload; forwards to Kafka producer |
| `kafka_producer.py` | Initializes `KafkaProducer`; routes to topic based on event type |

#### Webhook Server API

The bridge does **not** use custom headers. ThingsBoard does not add custom headers to webhook requests by default. The bridge determines event type by parsing the ThingsBoard payload structure:

```
POST /events
  Body: { ... ThingsBoard event payload ... }
  Response: 202 Accepted
```

**Event type detection** (inside the payload, not headers):

ThingsBoard webhooks include a `type` field in the event payload that identifies the event:

```json
{
  "type": "POST_TELEMETRY_REQUEST",
  "entityId": { "type": "DEVICE", "id": "..." },
  "body": { ... telemetry data ... }
}
```

The bridge inspects `event.type` to route to the correct Kafka topic. If the field is missing or unrecognized, the bridge responds with `400 Bad Request`.

#### Event Routing

| Event Type | Kafka Topic |
|------------|-------------|
| `POST_TELEMETRY_REQUEST` | `thingsboard.telemetry` |
| `ALARM` | `thingsboard.alarm` |
| `ATTRIBUTE_UPDATE` | `thingsboard.attributes` |

#### ThingsBoard Rule Engine Configuration

A webhook node must be configured in ThingsBoard:

1. Open ThingsBoard UI → **Rule Chains**
2. Create or select rule chain
3. Add **Webhook** node:
   - URL: `http://thingsboard-kafka-bridge:8086/events`
   - Method: `POST`
   - Payload: Full message body
   - Forward failed messages: `false`
4. Wire from **All Messages** to the Webhook node

---

## 3. Data Flow

### 3.1 Sensor Data Flow (Simulator → Infrastructure)

```
┌──────────────────────────┐
│   Sensor Simulator       │
│   (asyncio, 10 machines) │
└──────┬──────────┬────────┘
       │          │
       ▼          ▼
  ┌────────┐  ┌──────────┐
  │ MQTT   │  │  Kafka   │
  │(M3)    │  │  (M2)    │
  └───┬────┘  └────┬─────┘
      │            │
      ▼            ▼
┌────────────────────────────┐
│        ThingsBoard          │
│  (MQTT broker + Rule Engine)│
└──────┬─────────────────────┘
       │
       ▼
┌────────────────────────────┐
│   Webhook → Kafka Bridge   │
│  (HTTP 8086)               │
└──────┬─────────────────────┘
       │
       ▼
┌────────────────────────────┐
│          Kafka              │
│  (topics: telemetry, alarm) │
└────────────────────────────┘
       │
       ▼
┌────────────────────────────┐
│       PostgreSQL            │
│   (ThingsBoard stores data) │
└────────────────────────────┘
```

### 3.2 Degradation Timeline

```
Machine Age (hours) → Sensor Behavior
─────────────────────────────────────────────
0–100h   : Stable, near nominal values
100–500h : Gradual drift begins (temperature rises, vibration increases)
500–1000h: Wear accelerates (vibration grows as √t, RPM variance widens)
1000h+   : Frequent alarm events, health < 30%, sensor instability
```

### 3.3 Kafka Topic Schema

Kafka uses the **same flat schema** as MQTT. No nested `telemetry` object.

```
Topic: iot.sensors.raw

Key:       machine_id (string, e.g., "machine-3")
Value:     JSON
  {
    "Temperature": 72.45,
    "Vibration": 5.23,
    "Pressure": 3.87,
    "RPM": 1380.0,
    "Humidity": 55.2,
    "MachineHealth": 78.4,
    "timestamp": 1699999999123,
    "machine_id": "machine-3",
    "alarms": ["Temperature"]
  }
```

---

## 4. Configuration

### 4.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BROKER` | `localhost:9092` | Kafka bootstrap server |
| `ZOOKEEPER_HOST` | `zookeeper:2181` | ZooKeeper connection string |
| `BOOTSTRAP_SERVERS` | `kafka:29092` | Internal Kafka address (Docker) |
| `MQTT_BROKER` | `localhost` | ThingsBoard MQTT broker |
| `MQTT_PORT` | `1884` | ThingsBoard MQTT port |
| `MQTT_TOPIC` | `v1/devices/me/telemetry` | MQTT ingestion topic |
| `SENSOR_INTERVAL` | `5` | Seconds between sensor reads |
| `MACHINE_COUNT` | `10` | Number of simulated machines |
| `DEGRADATION_SPEED` | `1` | Machine hours per real second |
| `TOPIC_RAW` | `iot.sensors.raw` | Kafka topic for raw sensor data |
| `TOPIC_TELEMETRY` | `thingsboard.telemetry` | Kafka topic for ThingsBoard telemetry |
| `TOPIC_ALARM` | `thingsboard.alarm` | Kafka topic for ThingsBoard alarms |
| `BRIDGE_PORT` | `8086` | Kafka Bridge HTTP port |

### 4.2 Docker Services Summary

| Service | Image | Port(s) | Role |
|---------|-------|---------|------|
| `postgresql` | `postgres:16` | `5432` | Persistent storage for ThingsBoard |
| `pgadmin` | `dpage/pgadmin4` | `5050` | PostgreSQL admin UI |
| `thingsboard-ce` | `thingsboard/tb-node:4.3.0.1` | `8080, 7070, 1884, 8883, 5683-5688` | IoT platform (UI, MQTT, CoAP, HTTP) |
| `zookeeper` | `confluentinc/cp-zookeeper:7.5.0` | `2181` | Kafka cluster coordination |
| `kafka` | `confluentinc/cp-kafka:7.5.0` | `9092` | Kafka message broker |
| `kafka-ui` | `optiflows/kafka-ui:latest` | `8085` | Kafka cluster management UI |
| `thingsboard-kafka-bridge` | custom | `8086` | HTTP webhook → Kafka bridge |

---

## 5. Dependencies

### 5.1 Sensor Simulator Python Dependencies

```txt
paho-mqtt>=2.0.0
confluent-kafka>=2.0.0
```

### 5.2 Kafka Bridge Python Dependencies

```txt
confluent-kafka>=2.0.0
flask>=3.0.0
```

---

## 6. Testing Strategy

### 6.1 Unit Tests
- `test_degradation_models.py` — Verify degradation functions return expected ranges
- `test_machine_state.py` — Verify health score calculation, alarm thresholds
- `test_kafka_producer.py` — Verify message serialization and topic routing

### 6.2 Integration Tests
- `test_sensor_publishing.py` — Verify data reaches ThingsBoard MQTT
- `test_kafka_bridge.py` — Verify webhook → Kafka flow
- `test_end_to_end.py` — Full pipeline: simulator → MQTT → ThingsBoard → webhook → Kafka

### 6.3 Load Tests
- Simulate 100+ machines to verify MQTT broker throughput
- Verify Kafka consumer lag under high write rate

---

## 7. Operational Considerations

### 7.1 Logging

All components write structured JSON logs. Log level configurable via `LOG_LEVEL` env var.

**Log entry schema:**

```json
{
  "timestamp": "2024-11-15T10:30:00.123Z",
  "level": "INFO",
  "component": "sensor_simulator",
  "machine_id": "machine-3",
  "message": "Published telemetry",
  "request_id": "a1b2c3d4"
}
```

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 with milliseconds, UTC |
| `level` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `component` | string | Module name: `sensor_simulator`, `mqtt_publisher`, `kafka_publisher`, `webhook_server`, `kafka_producer` |
| `message` | string | Human-readable description |
| `machine_id` | string (optional) | Machine identifier when applicable |
| `request_id` | string (optional) | Correlation ID for webhook requests |

**Bridge logs HTTP requests** with `request_id` generated via `uuid4` for end-to-end traceability.

### 7.2 Health Checks
- Docker Compose health checks for all services
- Kafka bridge exposes `/healthz` endpoint

### 7.3 Restart Policy
- All services: `restart: always`
- Kafka: `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1` (single broker, acceptable for dev)

### 7.4 Data Retention
- PostgreSQL: ThingsBoard default data retention (configurable)
- Kafka: `log.retention.hours=168` (1 week default for dev)
- pgAdmin: Stateless, no persistent data (optional volume)

---

## 8. File Index

```
docker-compose.yml                          — Container orchestration
Makefile                                    — Build/run commands
.env                                        — Environment configuration
sensors/
├── __init__.py                             — Package marker
├── requirements.txt                        — Python dependencies
├── sensor_simulator.py                     — Main entry (asyncio orchestrator)
├── mqtt_publisher.py                       — MQTT client for ThingsBoard
├── kafka_publisher.py                      — Kafka producer for raw data
├── degradation_models.py                   — Wear/tear math functions
├── machine_state.py                        — Per-machine state + health
thingsboard-kafka-bridge/
├── __init__.py                             — Package marker
├── requirements.txt                        — Python dependencies
├── webhook_server.py                       — HTTP webhook receiver
├── kafka_producer.py                       — Kafka producer for bridge
```
