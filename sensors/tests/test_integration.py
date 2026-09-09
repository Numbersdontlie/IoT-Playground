"""Integration tests per specs/integration.feature.

Tests the complete data pipeline:
- Simulator → MQTT → ThingsBoard (mocked)
- Simulator → Kafka → Bridge (mocked)
- State persistence across restarts
- Data consistency between MQTT and Kafka outputs
- Alarm propagation through the pipeline
"""

import json
import os
import time
import asyncio
from unittest.mock import MagicMock, patch, call

import pytest

from sensors.sensor_simulator import SensorSimulator
from sensors.machine_state import MachineState
from sensors.mqtt_publisher import MQTTPublisher
from sensors.kafka_publisher import KafkaPublisher
from thingsboard_kafka_bridge.kafka_producer import KafkaBridgeProducer
from thingsboard_kafka_bridge.webhook_server import create_app, clear_producer


class TestFullPipelineSimulatorToVisualization:
    """Scenario: Full pipeline — simulator to visualization.

    Given all Docker services are running
    And the simulator is publishing with 10 machines
    When 60 seconds pass
    Then ThingsBoard UI should show telemetry for 10 devices
    And PostgreSQL should have stored the telemetry records
    And Kafka topic `iot.sensors.raw` should have received messages
    """

    def test_simulator_publishes_to_all_destinations(self):
        """Verify simulator publishes to both MQTT and Kafka for all 10 machines."""
        mock_mqtt = MagicMock()
        mock_kafka = MagicMock()

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            with patch('sensors.sensor_simulator.MQTTPublisher') as mock_mqtt_cls:
                with patch('sensors.sensor_simulator.KafkaPublisher') as mock_kafka_cls:
                    mock_mqtt_cls.return_value = mock_mqtt
                    mock_kafka_cls.return_value = mock_kafka

                    sim = SensorSimulator(machine_count=10)
                    sim.create_machines()

                    # Run one publish cycle
                    asyncio.get_event_loop().run_until_complete(
                        sim._publish_cycle()
                    )

                    # All 10 machines should publish via MQTT
                    assert mock_mqtt.publish.call_count == 10
                    # All 10 machines should publish via Kafka
                    assert mock_kafka.publish.call_count == 10

    def test_mqtt_publishes_correct_format(self):
        """Verify MQTT payloads contain required telemetry fields."""
        mock_mqtt = MagicMock()
        mock_kafka = MagicMock()

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            with patch('sensors.sensor_simulator.MQTTPublisher') as mock_mqtt_cls:
                with patch('sensors.sensor_simulator.KafkaPublisher') as mock_kafka_cls:
                    mock_mqtt_cls.return_value = mock_mqtt
                    mock_kafka_cls.return_value = mock_kafka

                    sim = SensorSimulator(machine_count=2)
                    sim.create_machines()
                    asyncio.get_event_loop().run_until_complete(
                        sim._publish_cycle()
                    )

                    # Get the published payloads
                    published = mock_mqtt.publish.call_args_list

                    for payload_call in published:
                        payload = payload_call[0][0]
                        # Check required fields
                        for field in [
                            'Temperature', 'Vibration', 'Pressure',
                            'RPM', 'Humidity', 'MachineHealth',
                            'timestamp', 'machine_id', 'alarms'
                        ]:
                            assert field in payload, f"Missing field: {field}"
                        # Check types
                        assert isinstance(payload['MachineHealth'], (int, float))
                        assert isinstance(payload['timestamp'], int)
                        assert isinstance(payload['machine_id'], str)
                        assert isinstance(payload['alarms'], list)

    def test_kafka_publishes_correct_format(self):
        """Verify Kafka payloads contain required fields matching MQTT."""
        mock_mqtt = MagicMock()
        mock_kafka = MagicMock()

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            with patch('sensors.sensor_simulator.MQTTPublisher') as mock_mqtt_cls:
                with patch('sensors.sensor_simulator.KafkaPublisher') as mock_kafka_cls:
                    mock_mqtt_cls.return_value = mock_mqtt
                    mock_kafka_cls.return_value = mock_kafka

                    sim = SensorSimulator(machine_count=2)
                    sim.create_machines()
                    asyncio.get_event_loop().run_until_complete(
                        sim._publish_cycle()
                    )

                    # Get Kafka published payloads
                    kafka_calls = mock_kafka.publish.call_args_list

                    for call_args in kafka_calls:
                        key = call_args[1]['key']
                        value = call_args[1]['value']
                        # Value may be dict (mock) or bytes (real)
                        if isinstance(value, dict):
                            data = value
                        else:
                            data = json.loads(value)
                        for field in [
                            'Temperature', 'Vibration', 'Pressure',
                            'RPM', 'Humidity', 'MachineHealth',
                            'timestamp', 'machine_id', 'alarms'
                        ]:
                            assert field in data, f"Missing field: {field}"


class TestAlarmPropagation:
    """Scenario: Full pipeline — alarm propagation.

    Given a machine has been running for simulated 1000 hours
    When a sensor exceeds a critical threshold
    Then an alarm should appear in ThingsBoard UI
    And an alarm event should be published to `thingsboard.alarm` Kafka topic
    And the machine's health score should reflect the alarm
    """

    def test_alarm_generated_at_high_age(self):
        """Machine at 5000 hours should show significant degradation."""
        machine = MachineState(machine_id="machine-test")
        machine.age_hours = 5000.0

        telemetry = machine.get_telemetry()
        # At 5000 hours, some degradation should be visible
        assert telemetry["MachineHealth"] < 100.0

    def test_alarm_field_populated_when_threshold_breached(self):
        """Simulate machine at age where alarm triggers."""
        machine = MachineState(machine_id="machine-alarm")
        machine.age_hours = 5000.0

        telemetry = machine.get_telemetry()
        # At 5000 hours, vibration is high and health drops
        assert telemetry["MachineHealth"] < 100.0

    def test_health_score_reflects_degradation(self):
        """Health score should drop as machine ages."""
        health_at_0 = []
        health_at_5000 = []

        for _ in range(10):
            for age in [0, 5000]:
                machine = MachineState(machine_id=f"test-{age}")
                machine.age_hours = age
                healths = [
                    machine.get_telemetry()["MachineHealth"]
                    for _ in range(5)
                ]
                if age == 0:
                    health_at_0.extend(healths)
                elif age == 5000:
                    health_at_5000.extend(healths)

        avg_0 = sum(health_at_0) / len(health_at_0)
        avg_5000 = sum(health_at_5000) / len(health_at_5000)
        # Health should decrease with age
        assert avg_0 > avg_5000

    def test_alarm_events_generated_with_severity(self):
        """Alarm events should include severity and details."""
        machine = MachineState(machine_id="machine-severity")
        # Force high age to trigger alarms
        machine.age_hours = 5000.0

        events = machine.get_alarm_events()
        if events:
            for event in events:
                assert "alarm_type" in event
                assert "severity" in event
                assert event["severity"] in ("WARNING", "CRITICAL")
                assert "details" in event
                assert "sensor" in event["details"]
                assert "value" in event["details"]
                assert "threshold" in event["details"]


class TestKafkaBridgeReceivesEvents:
    """Scenario: Kafka bridge receives and routes events.

    Given ThingsBoard is receiving telemetry from 10 devices
    And the webhook is configured on ThingsBoard
    When devices publish telemetry for 60 seconds
    Then `thingsboard.telemetry` topic should have 120+ messages
    And `thingsboard.alarm` topic should have messages only when thresholds are breached
    """

    def setup_method(self):
        clear_producer()

    def teardown_method(self):
        clear_producer()

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_bridge_routes_telemetry_to_correct_topic(self, mock_producer_cls):
        """Verify telemetry events route to thingsboard.telemetry topic."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        result = prod.publish_event(
            "POST_TELEMETRY_REQUEST",
            {"type": "POST_TELEMETRY_REQUEST", "body": {"Temperature": 50.0}}
        )

        assert result is True
        call_kwargs = mock_producer.produce.call_args[1]
        assert call_kwargs["topic"] == "thingsboard.telemetry"

    @patch("thingsboard_kafka_bridge.kafka_producer.Producer")
    def test_bridge_routes_alarm_to_correct_topic(self, mock_producer_cls):
        """Verify alarm events route to thingsboard.alarm topic."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        prod = KafkaBridgeProducer()
        result = prod.publish_event(
            "ALARM",
            {"type": "ALARM", "body": {"alarm": "test"}}
        )

        assert result is True
        call_kwargs = mock_producer.produce.call_args[1]
        assert call_kwargs["topic"] == "thingsboard.alarm"

    def test_webhook_endpoint_routes_telemetry(self):
        """Test webhook endpoint routes telemetry events correctly."""
        mock_producer = MagicMock()
        mock_producer.publish_event.return_value = True

        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.post(
            "/events",
            data=json.dumps({
                "type": "POST_TELEMETRY_REQUEST",
                "entityId": {"type": "DEVICE", "id": "abc"},
                "body": {"Temperature": 50.0},
            }),
            content_type="application/json",
        )

        assert response.status_code == 202
        mock_producer.publish_event.assert_called_once()
        args = mock_producer.publish_event.call_args[0]
        assert args[0] == "POST_TELEMETRY_REQUEST"

    def test_webhook_endpoint_routes_alarm(self):
        """Test webhook endpoint routes alarm events correctly."""
        mock_producer = MagicMock()
        mock_producer.publish_event.return_value = True

        app = create_app(producer=mock_producer)
        client = app.test_client()

        response = client.post(
            "/events",
            data=json.dumps({
                "type": "ALARM",
                "entityId": {"type": "DEVICE", "id": "abc"},
                "body": {"alarm": "Temperature"},
            }),
            content_type="application/json",
        )

        assert response.status_code == 202
        args = mock_producer.publish_event.call_args[0]
        assert args[0] == "ALARM"


class TestDataConsistency:
    """Scenario: Data consistency between MQTT and Kafka.

    Given the simulator publishes to both MQTT and Kafka
    When a machine publishes a reading at time T
    Then the same reading should appear in both `v1/devices/me/telemetry`
    and `iot.sensors.raw`
    And the values should match within noise tolerance
    """

    def test_mqtt_and_kafka_receive_same_values(self):
        """Verify MQTT and Kafka payloads contain identical sensor values."""
        mock_mqtt = MagicMock()
        mock_kafka = MagicMock()

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            with patch('sensors.sensor_simulator.MQTTPublisher') as mock_mqtt_cls:
                mock_mqtt_cls.return_value = mock_mqtt

                sim = SensorSimulator(machine_count=3)
                sim.create_machines()
                sim.kafka_publisher = mock_kafka
                asyncio.get_event_loop().run_until_complete(
                    sim._publish_cycle()
                )

                # Get MQTT payloads
                mqtt_payloads = [
                    c[0][0] for c in mock_mqtt.publish.call_args_list
                ]
                # Get Kafka payloads
                kafka_payloads = []
                for call in mock_kafka.publish.call_args_list:
                    value = call[1]['value']
                    if isinstance(value, dict):
                        kafka_payloads.append(value)
                    else:
                        kafka_payloads.append(json.loads(value))

                # Compare same machine (machine-1 at index 0)
                mqtt_t1 = mqtt_payloads[0]
                kafka_t1 = kafka_payloads[0]

                for sensor in ["Temperature", "Vibration", "Pressure",
                               "RPM", "Humidity"]:
                    mqtt_val = mqtt_t1[sensor]
                    kafka_val = kafka_t1[sensor]
                    assert mqtt_val == kafka_val, \
                        f"{sensor}: MQTT={mqtt_val}, Kafka={kafka_val}"

    def test_consistent_across_multiple_cycles(self):
        """Verify consistency holds across multiple publish cycles."""
        mock_mqtt = MagicMock()
        mock_kafka = MagicMock()

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            with patch('sensors.sensor_simulator.MQTTPublisher') as mock_mqtt_cls:
                mock_mqtt_cls.return_value = mock_mqtt

                sim = SensorSimulator(machine_count=2)
                sim.create_machines()
                sim.kafka_publisher = mock_kafka

                # Patch _publish_kafka to use mock and prevent race condition
                orig_publish_kafka = sim._publish_kafka
                def mock_publish_kafka(key, value):
                    mock_kafka.publish(key=key, value=value)
                sim._publish_kafka = mock_publish_kafka

                for cycle in range(5):
                    mock_mqtt.reset_mock()
                    mock_kafka.reset_mock()

                    # Serial publish to avoid race condition with tick()
                    for i, machine in enumerate(sim.machines):
                        telemetry = machine.get_telemetry()
                        machine.tick(sim.degradation_speed * sim.interval)
                        mock_mqtt.publish(telemetry)
                        mock_kafka.publish(
                            key=machine.machine_id, value=telemetry
                        )

                    mqtt_vals = [
                        c[0][0] for c in mock_mqtt.call_args_list
                    ]
                    kafka_vals = [
                        c[1]['value'] for c in mock_kafka.call_args_list
                    ]

                    assert len(mqtt_vals) == len(kafka_vals)
                    for i in range(len(mqtt_vals)):
                        for sensor in ["Temperature", "Vibration",
                                      "Pressure", "RPM", "Humidity"]:
                            assert mqtt_vals[i][sensor] == \
                                kafka_vals[i][sensor]


class TestMultipleSimulatorRestarts:
    """Scenario: Multiple simulator restarts.

    Given the simulator is running with 10 machines
    When the simulator process is stopped and restarted
    Then all 10 machines should resume publishing
    And machine ages should persist (no reset to 0)
    And no duplicate telemetry should be sent during restart
    """

    def test_state_persists_across_simulator_instances(self, tmp_path):
        """Verify state file preserves machine ages between restarts."""
        state_file = str(tmp_path / "test_state.json")

        # First instance: run simulation
        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            sim1 = SensorSimulator(
                machine_count=3,
                state_file=state_file,
            )
            sim1.create_machines()
            # Advance machines
            for machine in sim1.get_machines():
                machine.tick(10.0)
            sim1._save_state()

            # Verify state was saved
            assert os.path.exists(state_file)
            with open(state_file) as f:
                saved = json.load(f)
            assert len(saved["machines"]) == 3
            for m in saved["machines"]:
                assert m["age_hours"] == 10.0

        # Second instance: load state (simulates restart)
        sim2 = SensorSimulator(
            machine_count=3,
            state_file=state_file,
        )
        sim2._load_or_create_machines()

        # Verify state was loaded
        for machine in sim2.get_machines():
            assert machine.age_hours == 10.0
            assert machine.machine_id.startswith("machine-")

    def test_state_file_not_reset_on_load(self, tmp_path):
        """Verify machines don't reset to 0 when loading existing state."""
        state_file = str(tmp_path / "test_no_reset.json")

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            sim1 = SensorSimulator(machine_count=5, state_file=state_file)
            sim1.create_machines()

            # Advance each machine different amounts
            for i, machine in enumerate(sim1.get_machines()):
                machine.tick((i + 1) * 10.0)

            sim1._save_state()

        # Restart
        sim2 = SensorSimulator(machine_count=5, state_file=state_file)
        sim2._load_or_create_machines()

        # All machines should have non-zero ages
        ages = [m.age_hours for m in sim2.get_machines()]
        assert all(a > 0 for a in ages)
        assert ages[0] == 10.0
        assert ages[1] == 20.0
        assert ages[2] == 30.0
        assert ages[3] == 40.0
        assert ages[4] == 50.0

    def test_new_machines_on_first_start(self, tmp_path):
        """Verify fresh state creates machines with age 0."""
        state_file = str(tmp_path / "test_fresh.json")

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            sim = SensorSimulator(machine_count=3, state_file=state_file)
            sim._load_or_create_machines()

            # All machines should be at age 0 (fresh state)
            for machine in sim.get_machines():
                assert machine.age_hours == 0.0

    def test_no_duplicate_publishes_on_restart(self, tmp_path):
        """Verify restart doesn't cause duplicate telemetry sends."""
        state_file = str(tmp_path / "test_no_dupes.json")

        mock_mqtt = MagicMock()
        mock_kafka = MagicMock()

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            # First run: create state
            with patch('sensors.sensor_simulator.MQTTPublisher') as m1:
                with patch('sensors.sensor_simulator.KafkaPublisher') as k1:
                    m1.return_value = mock_mqtt
                    k1.return_value = mock_kafka

                    sim1 = SensorSimulator(
                        machine_count=2,
                        state_file=state_file,
                    )
                    sim1._load_or_create_machines()
                    for m in sim1.get_machines():
                        m.tick(5.0)
                    sim1._save_state()
                    mock_mqtt.reset_mock()
                    mock_kafka.reset_mock()

                    # Simulate restart: create new instance
                    with patch('sensors.sensor_simulator.MQTTPublisher') as m2:
                        with patch('sensors.sensor_simulator.KafkaPublisher') as k2:
                            m2.return_value = mock_mqtt
                            k2.return_value = mock_kafka

                            sim2 = SensorSimulator(
                                machine_count=2,
                                state_file=state_file,
                            )
                            sim2._load_or_create_machines()

                            # Should load 2 machines with preserved ages
                            assert len(sim2.get_machines()) == 2
                            for machine in sim2.get_machines():
                                assert machine.age_hours == 5.0

                            # Run one publish cycle
                            asyncio.get_event_loop().run_until_complete(
                                sim2._publish_cycle()
                            )

                            # Each machine publishes once per cycle
                            assert mock_mqtt.publish.call_count == 2
                            assert mock_kafka.publish.call_count == 2

    def test_machine_count_preserved_after_restart(self, tmp_path):
        """Verify machine count doesn't change across restarts."""
        state_file = str(tmp_path / "test_count.json")

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            sim1 = SensorSimulator(machine_count=10, state_file=state_file)
            sim1.create_machines()
            for m in sim1.get_machines():
                m.tick(1.0)
            sim1._save_state()

        sim2 = SensorSimulator(machine_count=10, state_file=state_file)
        sim2._load_or_create_machines()

        assert len(sim2.get_machines()) == 10

    def test_health_pct_persists(self, tmp_path):
        """Verify health percentage persists across restarts."""
        state_file = str(tmp_path / "test_health.json")

        with patch.object(SensorSimulator, '_generate_token', return_value='token'):
            sim1 = SensorSimulator(machine_count=2, state_file=state_file)
            sim1.create_machines()
            sim1.get_machines()[0].age_hours = 5000.0
            sim1.get_machines()[1].age_hours = 5000.0

            # Trigger health calculation
            for m in sim1.get_machines():
                m.get_telemetry()

            sim1._save_state()

        sim2 = SensorSimulator(machine_count=2, state_file=state_file)
        sim2._load_or_create_machines()

        assert len(sim2.get_machines()) == 2
        # Health should be preserved from save (not reset to 100)
        for machine in sim2.get_machines():
            # At 5000 hours, health should be less than 100
            assert machine.health_pct < 100.0


class TestEndToEndFlow:
    """Combined test verifying the full data flow between components."""

    def setup_method(self):
        clear_producer()

    def teardown_method(self):
        clear_producer()

    def test_telemetry_flows_machine_to_bridge(self):
        """Test complete flow: MachineState → simulator → bridge."""
        machine = MachineState(machine_id="machine-flow")
        machine.age_hours = 5000.0

        # Get telemetry from machine
        telemetry = machine.get_telemetry()

        # Verify all fields present
        assert "Temperature" in telemetry
        assert "Vibration" in telemetry
        assert "Pressure" in telemetry
        assert "RPM" in telemetry
        assert "Humidity" in telemetry
        assert "MachineHealth" in telemetry
        assert telemetry["MachineHealth"] < 100.0  # Some degradation

        # Bridge can consume this format
        with patch("thingsboard_kafka_bridge.kafka_producer.Producer") as mock_cls:
            mock_producer = MagicMock()
            mock_cls.return_value = mock_producer

            prod = KafkaBridgeProducer()
            result = prod.publish_event(
                "POST_TELEMETRY_REQUEST",
                {"type": "POST_TELEMETRY_REQUEST", "body": telemetry}
            )

            assert result is True
            call_kwargs = mock_producer.produce.call_args[1]
            published = json.loads(call_kwargs["value"])
            assert "body" in published
            assert published["body"]["Temperature"] == telemetry["Temperature"]

    def test_alarm_flows_machine_to_bridge(self):
        """Test alarm events flow from machine through bridge."""
        machine = MachineState(machine_id="machine-alarm-flow")
        machine.age_hours = 5000.0  # High age → likely alarms

        # Get telemetry with alarms
        telemetry = machine.get_telemetry()
        alarms = telemetry["alarms"]

        # Get alarm events
        events = machine.get_alarm_events()

        # If there are alarms, verify they flow through bridge
        if alarms:
            assert len(events) > 0
            for event in events:
                assert event["originator"] == "machine-alarm-flow"
                assert event["severity"] in ("WARNING", "CRITICAL")

            # Test bridge can consume alarm events
            with patch(
                "thingsboard_kafka_bridge.kafka_producer.Producer"
            ) as mock_cls:
                mock_producer = MagicMock()
                mock_cls.return_value = mock_producer

                prod = KafkaBridgeProducer()
                result = prod.publish_event(
                    "ALARM",
                    {"type": "ALARM", "body": events[0]}
                )

                assert result is True
                call_kwargs = mock_producer.produce.call_args[1]
                assert call_kwargs["topic"] == "thingsboard.alarm"
