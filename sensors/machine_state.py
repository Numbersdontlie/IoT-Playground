"""Machine state tracking for industrial IoT simulation.

Each MachineState represents a simulated industrial machine with its own
degradation trajectory, health score, and sensor readings.
"""

import time
import logging
from typing import Optional

from sensors.degradation_models import (
    temperature,
    vibration,
    pressure,
    rpm,
    humidity,
    check_alarms,
    calculate_machine_health,
)

logger = logging.getLogger(__name__)


class MachineState:
    """Encapsulates state for a single simulated machine.

    Attributes:
        machine_id: Unique identifier (e.g., "machine-1").
        age_hours: Operational age in hours, monotonically increasing.
        health_pct: Current health score (0-100).
        last_pressure_value: State required for pressure model.
    """

    def __init__(self, machine_id: str, initial_pressure: float = 4.0) -> None:
        """Initialize machine state.

        Args:
            machine_id: Unique machine identifier.
            initial_pressure: Starting pressure reading in bar.
        """
        self.machine_id = machine_id
        self.age_hours: float = 0.0
        self.health_pct: float = 100.0
        self.last_pressure_value: float = initial_pressure
        self._cached_sensor_values: Optional[dict] = None
        self._cached_timestamp: float = 0.0

    def tick(self, interval_hours: float) -> None:
        """Advance machine state by given hours.

        Args:
            interval_hours: Hours to advance (typically DEGRADATION_SPEED * interval).
        """
        self.age_hours += interval_hours
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Invalidate cached sensor values when state changes."""
        self._cached_sensor_values = None
        self._cached_timestamp = 0.0

    def _get_sensor_values(self) -> dict:
        """Get current sensor readings for all sensors (with caching).

        Sensor values are cached to ensure consistency between
        telemetry, alarm detection, and health score.

        Returns:
            Dict mapping sensor names to their current values.
        """
        if self._cached_sensor_values is not None:
            return self._cached_sensor_values

        self._cached_sensor_values = {
            "Temperature": temperature(self.age_hours),
            "Vibration": vibration(self.age_hours),
            "Pressure": self._get_pressure(),
            "RPM": rpm(self.age_hours),
            "Humidity": humidity(self.age_hours),
        }
        self._cached_timestamp = time.time()
        return self._cached_sensor_values

    def get_sensor_values(self) -> dict:
        """Get current sensor readings for all sensors.

        Returns:
            Dict mapping sensor names to their current values.
        """
        return self._get_sensor_values()

    def _get_pressure(self) -> float:
        """Get current pressure reading (stateful).

        Returns:
            Current pressure in bar.
        """
        self.last_pressure_value = pressure(
            self.age_hours, self.last_pressure_value
        )
        return self.last_pressure_value

    def get_telemetry(self) -> dict:
        """Get complete telemetry payload for this machine.

        Sensor values are evaluated once and cached to ensure
        consistency with alarm detection and health score.

        Returns:
            Dict containing all sensor values, health, timestamp, and alarms.
        """
        sensor_values = self._get_sensor_values()
        alarms = []
        for sensor_name, value in sensor_values.items():
            alarm_list = check_alarms(value, sensor_name)
            alarms.extend(alarm_list)

        self.health_pct = calculate_machine_health(sensor_values)

        telemetry = {
            "Temperature": sensor_values["Temperature"],
            "Vibration": sensor_values["Vibration"],
            "Pressure": sensor_values["Pressure"],
            "RPM": sensor_values["RPM"],
            "Humidity": sensor_values["Humidity"],
            "MachineHealth": self.health_pct,
            "timestamp": int(time.time() * 1000),
            "machine_id": self.machine_id,
            "alarms": alarms,
        }

        if alarms:
            logger.info(
                "Machine %s alarms: %s", self.machine_id, alarms
            )

        return telemetry

    def get_alarm_events(self) -> list:
        """Get alarm entity events for this machine.

        Uses the same cached sensor values as get_telemetry() for consistency.

        Returns:
            List of alarm event dicts (empty if no alarms).
        """
        sensor_values = self._get_sensor_values()
        events = []
        for sensor_name, value in sensor_values.items():
            alarms = check_alarms(value, sensor_name)
            for alarm_name in alarms:
                event = {
                    "alarm_type": alarm_name,
                    "severity": self._alarm_severity(alarm_name),
                    "originator": self.machine_id,
                    "start_ts": int(time.time() * 1000),
                    "end_ts": None,
                    "cleared": False,
                    "details": {
                        "sensor": sensor_name,
                        "value": value,
                        "threshold": self._get_threshold(sensor_name),
                    },
                }
                events.append(event)
        return events

    @staticmethod
    def _alarm_severity(alarm_name: str) -> str:
        """Determine severity from alarm name.

        Args:
            alarm_name: Alarm identifier (e.g., "WarningTemperature").

        Returns:
            "WARNING" or "CRITICAL".
        """
        if alarm_name.startswith("Critical"):
            return "CRITICAL"
        return "WARNING"

    @staticmethod
    def _get_threshold(sensor_name: str) -> float:
        """Get threshold value from alarm name.

        Args:
            alarm_name: Alarm identifier.

        Returns:
            Threshold value that was exceeded.
        """
        if "Critical" in alarm_name:
            if sensor_name == "Temperature":
                return 90.0
            elif sensor_name == "Vibration":
                return 25.0
            elif sensor_name == "Pressure":
                return 1.0
            elif sensor_name == "RPM":
                # RPM has both low and high critical thresholds
                return 500.0
            elif sensor_name == "Humidity":
                return 10.0
        else:  # Warning
            if sensor_name == "Temperature":
                return 75.0
            elif sensor_name == "Vibration":
                return 15.0
            elif sensor_name == "Pressure":
                return 1.5
            elif sensor_name == "RPM":
                return 800.0
            elif sensor_name == "Humidity":
                return 20.0
        return 0.0

    def __repr__(self) -> str:
        return (
            f"MachineState(id={self.machine_id}, "
            f"age={self.age_hours:.1f}h, "
            f"health={self.health_pct:.1f}%)"
        )
