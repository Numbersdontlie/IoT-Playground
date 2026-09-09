Feature: Degradation Models

  As a test operator,
  I want sensor readings to degrade realistically over machine age,
  So that I can test alarm generation and predictive maintenance logic.

  Scenario Outline: Temperature increases with age
    Given a machine at age <age> hours
    When I read the temperature sensor
    Then the value should be between <min>°C and <max>°C

    Examples:
      | age  | min  | max  |
      | 0    | 35   | 55   |
      | 100  | 38   | 60   |
      | 500  | 50   | 75   |
      | 1000 | 55   | 85   |
      | 2000 | 60   | 95   |

  Scenario Outline: Vibration increases with bearing wear
    Given a machine at age <age> hours
    When I read the vibration sensor
    Then the value should be between <min> mm/s and <max> mm/s

    Examples:
      | age  | min  | max  |
      | 0    | 1.0  | 4.0  |
      | 100  | 1.5  | 5.5  |
      | 500  | 3.0  | 8.0  |
      | 1000 | 4.5  | 12.0 |
      | 2000 | 6.0  | 16.0 |

  Scenario Outline: RPM decreases with motor wear
    Given a machine at age <age> hours
    When I read the RPM sensor
    Then the mean value should be between <min> and <max> rev/min

    Examples:
      | age  | min  | max  |
      | 0    | 1450 | 1550 |
      | 500  | 1425 | 1525 |
      | 1000 | 1400 | 1500 |
      | 2000 | 1350 | 1450 |

  Scenario Outline: Humidity drifts with calibration loss
    Given a machine at age <age> hours
    When I read the humidity sensor
    Then the value should be between <min>% and <max>%

    Examples:
      | age  | min  | max  |
      | 0    | 38   | 62   |
      | 500  | 35   | 65   |
      | 1000 | 32   | 68   |
      | 2000 | 28   | 72   |

  Scenario: Pressure follows random walk with occasional spikes
    Given a machine at pressure <initial> bar
    When I simulate 100 hours of pressure readings
    Then the pressure should not change by more than <max_drift> bar
    And there should be at least 0 and at most 5 leak spike events

    Examples:
      | initial | max_drift |
      | 4.0     | 3.0       |
      | 6.0     | 4.0       |

  Scenario: Health score decreases as machines age
    Given 10 machines at various ages
    Then the aggregate health score should be between <min>% and <max>%

    Examples:
      | min_age | max_age | min | max |
      | 0       | 10      | 95  | 100 |
      | 100     | 200     | 80  | 95  |
      | 500     | 600     | 50  | 70  |
      | 1000    | 1100    | 20  | 40  |
