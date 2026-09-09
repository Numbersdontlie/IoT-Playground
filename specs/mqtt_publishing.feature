Feature: MQTT Publishing to ThingsBoard

  As an IoT data pipeline,
  I want sensor telemetry delivered to ThingsBoard via MQTT,
  So that the platform can ingest, store, and visualize the data.

  Scenario Outline: Simulator publishes telemetry via MQTT
    When the simulator is running with <count> machines
    Then each machine should publish telemetry every <interval> seconds
    And the payload should be valid JSON

    Examples:
      | count | interval |
      | 1     | 5        |
      | 10    | 5        |

  Scenario: Telemetry payload contains all required fields
    When a machine publishes telemetry
    Then the payload must contain:
      | Field          | Type   | Required |
      | Temperature    | number | yes      |
      | Vibration      | number | yes      |
      | Pressure       | number | yes      |
      | RPM            | number | yes      |
      | Humidity       | number | yes      |
      | MachineHealth  | number | yes      |
      | timestamp      | number | yes      |
      | machine_id     | string | yes      |

  Scenario: MQTT uses correct ThingsBoard topic
    When the simulator publishes telemetry
    Then the MQTT topic should be `v1/devices/me/telemetry`
    And the QoS level should be 1
    And the client username should be the device access token

  Scenario: MQTT connection survives broker restart
    Given the MQTT broker is running
    When the broker is restarted
    And the simulator continues running
    Then the simulator should reconnect within 30 seconds
    And no telemetry data should be lost during reconnection

  Scenario: Simulator handles broker unreachable
    Given the MQTT broker is not reachable
    When the simulator attempts to publish
    Then the simulator should log a connection error
    And the simulator should retry with exponential backoff
    And the simulator should not crash
