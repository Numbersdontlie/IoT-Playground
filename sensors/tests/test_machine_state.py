"""Tests for machine state management."""

import pytest
from sensors.machine_state import MachineState


class TestMachineStateInit:
    """Test MachineState initialization."""

    def test_initializes_with_machine_id(self):
        machine = MachineState(machine_id="machine-1")
        assert machine.machine_id == "machine-1"

    def test_initializes_at_zero_age(self):
        machine = MachineState(machine_id="machine-1")
        assert machine.age_hours == 0.0

    def test_initializes_at_full_health(self):
        machine = MachineState(machine_id="machine-1")
        assert machine.health_pct == 100.0

    def test_initializes_pressure_at_default(self):
        machine = MachineState(machine_id="machine-1")
        assert machine.last_pressure_value == 4.0

    def test_initializes_pressure_at_custom(self):
        machine = MachineState(machine_id="machine-1", initial_pressure=5.0)
        assert machine.last_pressure_value == 5.0


class TestMachineStateTick:
    """Test MachineState age progression."""

    def test_ticks_forward_age(self):
        machine = MachineState(machine_id="machine-1")
        machine.tick(10.0)
        assert machine.age_hours == 10.0

    def test_multiple_ticks_accumulate(self):
        machine = MachineState(machine_id="machine-1")
        machine.tick(5.0)
        machine.tick(5.0)
        machine.tick(10.0)
        assert machine.age_hours == 20.0

    def test_small_tick_values(self):
        machine = MachineState(machine_id="machine-1")
        machine.tick(0.1)
        assert machine.age_hours == pytest.approx(0.1, abs=0.01)


class TestMachineStateTelemetry:
    """Test telemetry generation per specs/sensor_simulation.feature."""

    def test_telemetry_contains_all_sensors(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        required_fields = [
            "Temperature", "Vibration", "Pressure",
            "RPM", "Humidity", "MachineHealth",
            "timestamp", "machine_id", "alarms",
        ]
        for field in required_fields:
            assert field in telemetry, f"Missing field: {field}"

    def test_telemetry_all_numbers(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        for field in ["Temperature", "Vibration", "Pressure", "RPM",
                      "Humidity", "MachineHealth"]:
            assert isinstance(telemetry[field], (int, float))

    def test_telemetry_timestamp_is_number(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        assert isinstance(telemetry["timestamp"], int)

    def test_telemetry_machine_id_matches(self):
        machine = MachineState(machine_id="machine-5")
        telemetry = machine.get_telemetry()
        assert telemetry["machine_id"] == "machine-5"

    def test_telemetry_alarms_is_list(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        assert isinstance(telemetry["alarms"], list)

    def test_new_machine_has_no_alarms(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        assert telemetry["alarms"] == []


class TestMachineStateSensorValues:
    """Test sensor values are within expected ranges."""

    def test_temperature_range(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        temp = telemetry["Temperature"]
        assert 35 <= temp <= 55

    def test_vibration_range(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        vib = telemetry["Vibration"]
        assert 0 <= vib <= 5

    def test_pressure_range(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        pressure = telemetry["Pressure"]
        assert 0 <= pressure <= 10

    def test_rpm_range(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        rpm = telemetry["RPM"]
        assert 1400 <= rpm <= 1600

    def test_humidity_range(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        hum = telemetry["Humidity"]
        assert 35 <= hum <= 65

    def test_machine_health_initial(self):
        machine = MachineState(machine_id="machine-1")
        telemetry = machine.get_telemetry()
        health = telemetry["MachineHealth"]
        assert 0 <= health <= 100
        # New machine should be near 100
        assert health > 80


class TestMachineStateRepr:
    """Test string representation."""

    def test_repr_contains_machine_id(self):
        machine = MachineState(machine_id="machine-3")
        assert "machine-3" in repr(machine)

    def test_repr_contains_age(self):
        machine = MachineState(machine_id="machine-1")
        assert "age=" in repr(machine)

    def test_repr_contains_health(self):
        machine = MachineState(machine_id="machine-1")
        assert "health=" in repr(machine)
