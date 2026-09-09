Feature: Sensor Simulation

  As an IoT platform operator,
  I want simulated machines generating realistic sensor data,
  So that I can test my IoT pipeline end-to-end.

  Background:
    Given the sensor simulator is configured with 10 machines
    And each machine starts at 0 operational hours
    And degradation speed is 1 machine-hour per real second
    And sensor interval is 5 seconds

  Scenario Outline: Simulated machines generate sensor data
    When I start the simulator with <count> machines
    Then each machine should produce sensor readings every <interval> seconds

    Examples:
      | count | interval |
      | 1     | 5        |
      | 5     | 5        |
      | 10    | 5        |
      | 10    | 1        |

  Scenario Outline: New machines start at nominal values
    When I start the simulator with <count> machines
    Then the initial readings should be near nominal values:

      | Sensor    | Nominal Value    | Tolerance |
      | Temperature | 45.0°C         | ±10°C     |
      | Vibration   | 2.5 mm/s       | ±1.0 mm/s |
      | Pressure    | 4.0 bar        | ±1.0 bar  |
      | RPM         | 1500 rev/min   | ±50 rev/min|
      | Humidity    | 50.0 %RH       | ±10 %RH   |

    Examples:
      | count |
      | 1     |
      | 5     |
      | 10    |

  Scenario Outline: Machines age independently
    When I run the simulator for <duration> seconds
    Then each machine's age should be approximately <expected_age> hours

    Examples:
      | duration | expected_age |
      | 30       | 30           |
      | 60       | 60           |
      | 300      | 300          |
