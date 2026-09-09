# Architecture — IoT Playground

## 1. System Context

```
┌─────────────────────────────────────────────────────────────┐
│                    OPERATOR / ANALYST                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ ThingsBoard  │  │ Kafka UI     │  │  pgAdmin         │  │
│  │ :8080 (UI)   │  │ :8085 (topics)│ │ :5050 (DB)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ queries / admin
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                        PLATFORM LAYER                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  ThingsBoard  │  │  Kafka       │  │  PostgreSQL        │  │
│  │  MQTT broker │  │  Streaming   │  │  (8.16 GB limit)   │  │
│  │  Rule Engine │  │  (168h ret.) │  │                    │  │
│  │  REST API    │  │              │  │                    │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘  │
│         │                 │                    │              │
│  ┌──────▼───────┐  ┌──────▼───────┐            │              │
│  │  Kafka Bridge │  │ Sensor       │            │              │
│  │  :8086        │  │ Simulator    │            │              │
│  │  (Python)     │  │ (Python)     │            │              │
│  └──────────────┘  └──────────────┘            │              │
└──────────────────────────────────────────────────────────────┘
                           │ MQTT / Kafka
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                      DEVICE LAYER                             │
│  ┌────────┐ ┌────────┐ ┌────────┐  ┌────────┐              │
│  │Machine1│ │Machine2│ │Machine3│ … │Machine10│              │
│  │ Sensors│ │ Sensors│ │ Sensors│   │ Sensors│              │
│  └────────┘ └────────┘ └────────┘  └────────┘              │
└──────────────────────────────────────────────────────────────┘
```

## 2. Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        sensor_simulator.py                      │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ MachineState │  │ MachineState │  │ MachineState │  …        │
│  │ machine-1    │  │ machine-2    │  │ machine-3    │           │
│  │ ─────        │  │ ─────        │  │ ─────        │            │
│  │ age: 342h    │  │ age: 128h    │  │ age: 890h    │            │
│  │ health: 78%  │  │ health: 94%  │  │ health: 32%  │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                  │                  │                   │
│         ▼                  ▼                  ▼                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                  Degradation Models                       │    │
│  │  temp() │ vibration() │ pressure() │ rpm() │ humidity()  │    │
│  └──────────────────────────┬───────────────────────────────┘    │
│                             │                                     │
│              ┌──────────────┴──────────────┐                     │
│              ▼                              ▼                     │
│      ┌──────────────┐              ┌──────────────┐              │
│      │ MQTT Pub     │              │ Kafka Pub    │              │
│      │ → ThingsBoard│              │ → Kafka      │              │
│      │ :1884        │              │ :9092        │              │
│      └──────┬───────┘              └──────────────┘              │
└─────────────┼───────────────────────────────────────────────────┘
              │
              ▼
      ┌─────────────────┐
      │   ThingsBoard    │
      │  (MQTT + Rule   │
      │   Engine)       │
      └───────┬─────────┘
              │ Webhook
              ▼
      ┌─────────────────┐
      │ Kafka Bridge     │
      │ (HTTP → Kafka)   │
      └───────┬─────────┘
              │
              ▼
      ┌─────────────────┐
      │     Kafka        │
      │  ┌────────────┐  │
      │  │telemetry   │  │
      │  │alarm       │  │
      │  └────────────┘  │
      └─────────────────┘
              │
              ▼
      ┌─────────────────┐
      │  PostgreSQL      │
      │  (ThingsBoard    │
      │   stores data)   │
      └─────────────────┘
```

## 3. Runtime Architecture

### 3.1 Simulator Runtime

```
asyncio event loop
├── asyncio.gather(*[machine.run() for machine in machines])
│   ├── machine-1: publish_telemetry() → MQTT + Kafka (every 5s)
│   ├── machine-2: publish_telemetry() → MQTT + Kafka (every 5s)
│   ├── ...
│   └── machine-10: publish_telemetry() → MQTT + Kafka (every 5s)
│
└── asyncio.create_task(health_monitor())
    └── Every 30s: recalculate health scores, log state
```

### 3.2 Bridge Runtime

```
Flask app
├── POST /events          → webhook handler → Kafka producer
├── POST /healthz         → health check
└── Background tasks:
    └── Kafka producer flush on exit
```

## 4. Deployment Topology

```
┌─────────────────────────────────────────────────────────────────┐
│  Docker Network: IoT_network (bridge)                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Host Ports (accessible from developer machine)          │   │
│  │                                                          │   │
│  │  localhost:5432  → PostgreSQL                            │   │
│  │  localhost:5050  → pgAdmin                               │   │
│  │  localhost:8080  → ThingsBoard Web UI                    │   │
│  │  localhost:8085  → Kafka UI                              │   │
│  │  localhost:8086  → Kafka Bridge (webhook target)         │   │
│  │  localhost:1884  → ThingsBoard MQTT                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────┐ ┌────────┐ ┌────────────┐ ┌──────────┐          │
│  │ PostgreSQL│ │Things- │ │ Kafka      │ │  Bridge  │          │
│  │ :5432    │ │ Board  │ │ :9092      │ │ :8086    │          │
│  └──────────┘ └────────┘ └────────────┘ └──────────┘          │
│         ▲          ▲             ▲              ▲               │
│         │          │             │              │               │
│  ┌──────┴──────────┴─────────────┴──────────────┴──────────┐   │
│  │           Internal: Docker networking                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 5. Data Flow Diagrams

### 5.1 Sensor Telemetry Flow

```
Simulator (async)
  │
  ├─[MQTT]──→ ThingsBoard
  │           │
  │           ├─→ PostgreSQL (persistent storage)
  │           │
  │           └─→ Rule Engine
  │                 │
  │                 └─[Webhook]──→ Kafka Bridge
  │                               │
  │                               └─[Kafka]──→ thingsboard.telemetry topic
  │
  └─[Kafka]──→ Kafka Broker
                │
                └──→ iot.sensors.raw topic
```

### 5.2 Alarm Flow

```
Sensor reads value → Threshold exceeded
  │
  ├─[MQTT]──→ ThingsBoard (telemetry with alarm field)
  │           │
  │           └─→ Rule Engine creates Alarm entity
  │
  └─[Webhook]──→ Kafka Bridge
                  │
                  └─[Kafka]──→ thingsboard.alarm topic
```

## 6. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Simulation | Python 3.10+ | Async sensor generation |
| MQTT | paho-mqtt | Device → ThingsBoard protocol |
| Streaming | Apache Kafka 7.5 | Event streaming |
| Coordination | ZooKeeper | Kafka cluster management |
| IoT Platform | ThingsBoard 4.3 | Device management, UI, rules |
| Storage | PostgreSQL 16 | Persistent telemetry storage |
| Bridge | Flask + confluent-kafka | ThingsBoard → Kafka |
| Orchestration | Docker Compose | Service management |

## 7. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| ThingsBoard MQTT down | Simulator continues, Kafka writes succeed, MQTT retries | Exponential backoff in MQTT publisher |
| Kafka broker down | MQTT still works, simulator logs warnings | Non-blocking Kafka publish (fire-and-forget or queue) |
| Bridge down | ThingsBoard telemetry reaches DB, but not Kafka | ThingsBoard retries webhook; Kafka gap is acceptable |
| PostgreSQL down | ThingsBoard rejects new data | Health check alerts; simulator can still stream to Kafka |
