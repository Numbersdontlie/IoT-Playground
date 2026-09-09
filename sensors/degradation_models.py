"""Sensor degradation models for industrial machines.

Models:
- Pure functions (no side effects): temperature, vibration, rpm, humidity
- Stateful function: pressure (requires last_value from caller)

All models add noise using random.gauss(0, sigma) and never seed globally.
Models should never mutate state (except pressure, which requires last_value).

Sensor thresholds for alarm generation:
- Temperature: warning > 75°C, critical > 90°C
- Vibration: warning > 15 mm/s, critical > 25 mm/s
- Pressure: warning < 1.5 bar, critical < 1.0 bar
- RPM: warning > 2200 or < 800 rev/min, critical > 2500 or < 500 rev/min
- Humidity: warning < 20% or > 80% RH, critical < 10% or > 90% RH
"""

import math
import random


# Alarm thresholds: (warning_lower, warning_upper, critical_lower, critical_upper)
ALARM_THRESHOLDS = {
    "Temperature": (75.0, 90.0, None, None),
    "Vibration": (15.0, 25.0, None, None),
    "Pressure": (1.0, 1.5, 1.5, None),
    "RPM": (800.0, 2200.0, 500.0, 2500.0),
    "Humidity": (10.0, 80.0, 20.0, 90.0),
}


def temperature(age_hours: float) -> float:
    """Temperature model with thermal drift and daily oscillation.

    Args:
        age_hours: Operational age of the machine in hours.

    Returns:
        Temperature reading in °C.

    Physical meaning:
        - base (45.0): Normal operating temperature
        - drift (0.002): Thermal degradation rate per hour
        - oscillation (8.0, 24h): Daily temperature cycles
        - noise (σ=1.5): Sensor measurement noise
    """
    base = 45.0
    drift = 0.001 * age_hours
    oscillation = 10.0 * math.sin(2 * math.pi * age_hours / 24)
    noise = random.gauss(0, 2.0)
    return round(base + drift + oscillation + noise, 2)


def vibration(age_hours: float) -> float:
    """Vibration model with bearing wear following power-law degradation.

    Args:
        age_hours: Operational age of the machine in hours.

    Returns:
        Vibration amplitude in mm/s.

    Physical meaning:
        - initial (2.5): New bearing vibration level
        - wear (0.03): Bearing wear coefficient per sqrt(hour)
        - noise (σ=0.5): Measurement noise
        - spikes: Random shock events from bearing defects
    """
    initial = 2.5
    wear = 0.03 * math.sqrt(age_hours)
    noise = random.gauss(0, 0.5)
    spike = random.gauss(2.0, 1.0) if random.random() < 0.005 else 0.0
    return round(max(0, initial + wear + noise + spike), 2)


def pressure(age_hours: float, last_value: float) -> float:
    """Pressure model with random walk and rare leak events.

    Note: This is the only stateful model. State (last_value) is maintained
    by the caller (MachineState) and passed in on each call.

    Args:
        age_hours: Operational age of the machine in hours.
        last_value: Previous pressure reading in bar.

    Returns:
        Current pressure reading in bar.

    Physical meaning:
        - drift (σ=0.05): Random walk step (pressure fluctuation)
        - leak (exponential, P=0.001): Rare leak events causing pressure drops
    """
    drift = random.gauss(0, 0.05)
    leak = random.gauss(2.0, 0.5) if random.random() < 0.001 else 0.0
    return round(last_value + drift - leak, 2)


def rpm(age_hours: float) -> float:
    """RPM model with motor degradation and increasing variance.

    Args:
        age_hours: Operational age of the machine in hours.

    Returns:
        Motor speed in rev/min.

    Physical meaning:
        - nominal (1500): New motor speed
        - degradation (0.05): Slow speed decline per hour
        - variance_increase: Motor wobbling increases with age
        - noise (σ=15): Speed measurement noise
    """
    nominal = 1500.0
    degradation = 0.05 * age_hours
    variance_increase = 1 + 0.001 * age_hours
    noise = random.gauss(0, 15) * variance_increase
    return round(nominal - degradation + noise, 1)


def humidity(age_hours: float) -> float:
    """Humidity model with sensor calibration drift and daily cycles.

    Args:
        age_hours: Operational age of the machine in hours.

    Returns:
        Relative humidity in %RH.

    Physical meaning:
        - ambient (50.0): Baseline ambient humidity
        - calibration_drift (0.005): Sensor calibration loss per hour
        - periodic (10.0, 24h): Daily humidity cycles
        - noise (σ=1.0): Measurement noise
    """
    ambient = 50.0
    calibration_drift = 0.005 * age_hours
    periodic = 10 * math.sin(2 * math.pi * age_hours / 24)
    noise = random.gauss(0, 1.0)
    return round(ambient + calibration_drift + periodic + noise, 2)


def get_alarm_thresholds(sensor_name: str) -> tuple:
    """Get warning and critical thresholds for a sensor.

    Args:
        sensor_name: Name of the sensor (e.g., "Temperature").

    Returns:
        Tuple of (warning_threshold, critical_threshold).

    Raises:
        ValueError: If sensor_name is not recognized.
    """
    if sensor_name not in ALARM_THRESHOLDS:
        raise ValueError(f"Unknown sensor: {sensor_name}")

    warning, critical = ALARM_THRESHOLDS[sensor_name][:2]
    return (warning, critical)


def check_alarms(sensor_value: float, sensor_name: str) -> list:
    """Check if sensor value exceeds alarm thresholds.

    Args:
        sensor_value: Current sensor reading.
        sensor_name: Name of the sensor.

    Returns:
        List of alarm names triggered (may be empty).
    """
    alarms = []

    if sensor_name == "Temperature":
        if sensor_value > 90.0:
            alarms.append("CriticalTemperature")
        elif sensor_value > 75.0:
            alarms.append("WarningTemperature")
    elif sensor_name == "Vibration":
        if sensor_value > 25.0:
            alarms.append("CriticalVibration")
        elif sensor_value > 15.0:
            alarms.append("WarningVibration")
    elif sensor_name == "Pressure":
        if sensor_value < 1.0:
            alarms.append("CriticalPressure")
        elif sensor_value < 1.5:
            alarms.append("WarningPressure")
    elif sensor_name == "RPM":
        if sensor_value > 2500.0 or sensor_value < 500.0:
            alarms.append("CriticalRPM")
        elif sensor_value > 2200.0 or sensor_value < 800.0:
            alarms.append("WarningRPM")
    elif sensor_name == "Humidity":
        if sensor_value > 90.0 or sensor_value < 10.0:
            alarms.append("CriticalHumidity")
        elif sensor_value > 80.0 or sensor_value < 20.0:
            alarms.append("WarningHumidity")

    return alarms


def sensor_health(sensor_value: float, warning_threshold: float,
                  critical_threshold: float, invert: bool = False) -> float:
    """Calculate health score for a sensor reading.

    Args:
        sensor_value: Current sensor reading.
        warning_threshold: Warning threshold value.
        critical_threshold: Critical threshold value.
        invert: If True, lower values are worse (for pressure, RPM low-end).

    Returns:
        Health score from 100.0 (safe) to 0.0 (critical).
    """
    if invert:
        # For sensors where lower is worse
        if sensor_value >= warning_threshold:
            return 100.0
        elif sensor_value <= critical_threshold:
            return 0.0
        else:
            ratio = (warning_threshold - sensor_value) / (warning_threshold - critical_threshold)
            return max(0.0, min(100.0, ratio * 100.0))
    else:
        # For sensors where higher is worse
        if sensor_value <= warning_threshold:
            return 100.0
        elif sensor_value >= critical_threshold:
            return 0.0
        else:
            ratio = (sensor_value - warning_threshold) / (critical_threshold - warning_threshold)
            return max(0.0, min(100.0, 100.0 - ratio * 100.0))


def calculate_machine_health(sensor_values: dict) -> float:
    """Calculate weighted health score for a machine.

    Weights: Vibration 35%, Temperature 25%, RPM 20%, Pressure 15%, Humidity 5%

    Args:
        sensor_values: Dict of sensor_name -> value pairs.

    Returns:
        Weighted health score from 0.0 to 100.0.
    """
    weights = {
        "Vibration": 0.35,
        "Temperature": 0.25,
        "RPM": 0.2,
        "Pressure": 0.15,
        "Humidity": 0.05,
    }

    score = 0.0
    for sensor_name, weight in weights.items():
        if sensor_name not in sensor_values:
            continue

        value = sensor_values[sensor_name]

        if sensor_name in ("Humidity", "RPM"):
            # U-shaped: both extremes are bad
            low_w, high_w, low_c, high_c = ALARM_THRESHOLDS[sensor_name]
            health = sensor_health_u_shaped(value, low_w, low_c, high_w, high_c)
        elif sensor_name == "Pressure":
            # Monotonic: lower is worse
            warning, critical = ALARM_THRESHOLDS[sensor_name][:2]
            health = sensor_health(value, warning, critical, invert=True)
        else:
            # Monotonic: higher is worse (Temperature, Vibration)
            warning, critical = ALARM_THRESHOLDS[sensor_name][:2]
            health = sensor_health(value, warning, critical, invert=False)

        score += health * weight

    return round(score, 1)


def sensor_health_u_shaped(value: float, low_warning: float, low_critical: float,
                           high_warning: float, high_critical: float) -> float:
    """Health for sensors where both extremes are bad (e.g., humidity).

    Args:
        value: Current sensor reading.
        low_warning: Lower warning threshold.
        low_critical: Lower critical threshold.
        high_warning: Upper warning threshold.
        high_critical: Upper critical threshold.

    Returns:
        Health score 100.0 (safe) to 0.0 (critical).
    """
    # Safe zone
    if low_warning <= value <= high_warning:
        return 100.0

    # Below low_warning
    if value < low_warning:
        if value <= low_critical:
            return 0.0
        ratio = (low_warning - value) / (low_warning - low_critical)
        return max(0.0, min(100.0, 100.0 - ratio * 100.0))

    # Above high_warning
    if value > high_warning:
        if value >= high_critical:
            return 0.0
        ratio = (value - high_warning) / (high_critical - high_warning)
        return max(0.0, min(100.0, 100.0 - ratio * 100.0))

    return 100.0
