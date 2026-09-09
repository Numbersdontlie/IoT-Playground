"""Tests for sensor simulator per specs/sensor_simulation.feature."""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from sensors.sensor_simulator import SensorSimulator


class TestSimulatorInit:
    """Test simulator initialization."""

    def test_default_values(self):
        sim = SensorSimulator()
        assert sim.mqtt_broker == "localhost"
        assert sim.mqtt_port == 1884
        assert sim.mqtt_topic == "v1/devices/me/telemetry"
        assert sim.kafka_bootstrap == "localhost:9092"
        assert sim.kafka_topic == "iot.sensors.raw"
        assert sim.interval == 5
        assert sim.machine_count == 10
        assert sim.degradation_speed == 1
        assert sim.state_file == "machine_state.json"

    def test_custom_values(self):
        sim = SensorSimulator(
            mqtt_broker="custom",
            mqtt_port=1234,
            mqtt_topic="custom",
            kafka_bootstrap="custom:9092",
            kafka_topic="custom/topic",
            interval=10,
            machine_count=5,
            degradation_speed=2,
            state_file="/tmp/state.json",
        )
        assert sim.mqtt_broker == "custom"
        assert sim.mqtt_port == 1234
        assert sim.mqtt_topic == "custom"
        assert sim.kafka_bootstrap == "custom:9092"
        assert sim.kafka_topic == "custom/topic"
        assert sim.interval == 10
        assert sim.machine_count == 5
        assert sim.degradation_speed == 2
        assert sim.state_file == "/tmp/state.json"


class TestSimulatorCreateMachines:
    """Test machine creation.

    Scenario Outline: New machines start at nominal values
      When I start the simulator with <count> machines
      Then machines should be created with correct count
    """

    def test_creates_correct_count(self):
        sim = SensorSimulator(machine_count=5)
        sim.create_machines()
        assert len(sim.get_machines()) == 5
        assert len(sim.mqtt_publishers) == 5

    def test_machines_have_ids(self):
        sim = SensorSimulator(machine_count=3)
        sim.create_machines()
        ids = [m.machine_id for m in sim.get_machines()]
        assert ids == ["machine-1", "machine-2", "machine-3"]

    def test_machines_start_at_zero(self):
        sim = SensorSimulator(machine_count=10)
        sim.create_machines()
        for machine in sim.get_machines():
            assert machine.age_hours == 0.0

    def test_machines_start_at_full_health(self):
        sim = SensorSimulator(machine_count=10)
        sim.create_machines()
        for machine in sim.get_machines():
            assert machine.health_pct == 100.0

    def test_per_machine_mqtt_publishers(self):
        sim = SensorSimulator(machine_count=3)
        sim.create_machines()
        assert len(sim.mqtt_publishers) == 3
        for publisher in sim.mqtt_publishers:
            assert hasattr(publisher, "token")
            assert len(publisher.token) > 0


class TestSimulatorGetConfig:
    """Test configuration access."""

    def test_config_returns_dict(self):
        sim = SensorSimulator()
        config = sim.get_config()
        assert isinstance(config, dict)

    def test_config_contains_all_fields(self):
        sim = SensorSimulator()
        config = sim.get_config()
        required = [
            "mqtt_broker", "mqtt_port", "mqtt_topic",
            "kafka_bootstrap", "kafka_topic",
            "interval", "machine_count", "degradation_speed",
        ]
        for field in required:
            assert field in config


class TestSimulatorPublishing:
    """Test publishing behavior per specs/sensor_simulation.feature.

    Scenario Outline: Simulated machines generate sensor data
      When I start the simulator with <count> machines
      Then each machine should produce sensor readings every <interval> seconds
    """

    @patch("sensors.sensor_simulator.MQTTPublisher")
    @patch("sensors.sensor_simulator.KafkaPublisher")
    def test_publishes_all_machines(self, mock_kafka, mock_mqtt):
        """Each machine should publish telemetry."""
        mock_mqtt_instance = MagicMock()
        mock_mqtt.return_value = mock_mqtt_instance
        mock_kafka_instance = MagicMock()
        mock_kafka.return_value = mock_kafka_instance

        sim = SensorSimulator(machine_count=3)
        sim.create_machines()

        # Mock the executor-based publish methods
        with patch.object(sim, "_publish_mqtt") as mock_mqtt_pub:
            with patch.object(sim, "_publish_kafka") as mock_kafka_pub:
                asyncio.get_event_loop().run_until_complete(
                    sim._publish_cycle()
                )

                # Each machine should have been published
                assert mock_mqtt_pub.call_count == 3
                assert mock_kafka_pub.call_count == 3

    @patch("sensors.sensor_simulator.KafkaPublisher")
    def test_mqtt_publishers_have_tokens(self, mock_kafka):
        """Each MQTT publisher should have a unique token."""
        mock_kafka_instance = MagicMock()
        mock_kafka.return_value = mock_kafka_instance

        sim = SensorSimulator(machine_count=3)
        sim.create_machines()

        tokens = [p.token for p in sim.mqtt_publishers]
        # All tokens should be unique
        assert len(set(tokens)) == 3
        # All tokens should be non-empty
        assert all(len(t) > 0 for t in tokens)


class TestSimulatorAging:
    """Test machine aging per specs/sensor_simulation.feature.

    Scenario Outline: Machines age independently
      When I run the simulator for <duration> seconds
      Then each machine's age should be approximately <expected_age> hours

      Examples:
        | duration | expected_age |
        | 30       | 30           |
        | 60       | 60           |
        | 300      | 300          |
    """

    def test_aging_calculates_correctly(self):
        sim = SensorSimulator(
            machine_count=1,
            interval=5,
            degradation_speed=1,
        )
        sim.create_machines()
        machine = sim.get_machines()[0]

        # 30 seconds / 5 interval = 6 cycles
        # 6 cycles * 1 speed * 5 interval = 30 hours
        for _ in range(6):
            machine.get_telemetry()
            machine.tick(sim.degradation_speed * sim.interval)

        assert machine.age_hours == pytest.approx(30.0, abs=1.0)


class TestSimulatorStopping:
    """Test simulator stop."""

    def test_stops_running_flag(self):
        sim = SensorSimulator()
        sim._running = True
        sim.stop()
        assert sim._running is False


class TestSimulatorNominalValues:
    """Test nominal values at startup.

    Scenario Outline: New machines start at nominal values
      | Sensor    | Nominal    | Tolerance |
      | Temperature | 45.0°C   | ±10°C     |
      | Vibration   | 2.5 mm/s | ±1.0 mm/s |
      | Pressure    | 4.0 bar  | ±1.0 bar  |
      | RPM         | 1500     | ±50 rev/min|
      | Humidity    | 50.0 %RH | ±10 %RH   |
    """

    def test_temperature_nominal(self):
        sim = SensorSimulator(machine_count=1)
        sim.create_machines()
        telemetry = sim.get_machines()[0].get_telemetry()
        assert 35 <= telemetry["Temperature"] <= 55

    def test_vibration_nominal(self):
        sim = SensorSimulator(machine_count=1)
        sim.create_machines()
        telemetry = sim.get_machines()[0].get_telemetry()
        assert 1.0 <= telemetry["Vibration"] <= 4.0

    def test_pressure_nominal(self):
        sim = SensorSimulator(machine_count=1)
        sim.create_machines()
        telemetry = sim.get_machines()[0].get_telemetry()
        assert 3.0 <= telemetry["Pressure"] <= 5.0

    def test_rpm_nominal(self):
        sim = SensorSimulator(machine_count=1)
        sim.create_machines()
        telemetry = sim.get_machines()[0].get_telemetry()
        assert 1450 <= telemetry["RPM"] <= 1550

    def test_humidity_nominal(self):
        sim = SensorSimulator(machine_count=1)
        sim.create_machines()
        telemetry = sim.get_machines()[0].get_telemetry()
        assert 38 <= telemetry["Humidity"] <= 62


class TestSimulatorStatePersistence:
    """Test state persistence per integration.feature.

    Scenario: Multiple simulator restarts
      When simulator is stopped and restarted
      Then machine ages should persist (no reset to 0)
    """

    def test_generate_token_deterministic(self):
        token1 = SensorSimulator._generate_token("machine-1")
        token2 = SensorSimulator._generate_token("machine-1")
        token3 = SensorSimulator._generate_token("machine-2")
        assert token1 == token2
        assert token1 != token3
        assert len(token1) > 0

    def test_get_config_contains_state_file(self):
        sim = SensorSimulator()
        config = sim.get_config()
        assert "state_file" in config
        assert config["state_file"] == "machine_state.json"

    def test_config_state_file_custom(self):
        sim = SensorSimulator(state_file="/custom/path.json")
        config = sim.get_config()
        assert config["state_file"] == "/custom/path.json"
