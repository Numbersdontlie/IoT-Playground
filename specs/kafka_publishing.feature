Feature: Kafka Publishing from Simulator

  As a data engineer,
  I want raw sensor data streamed to Kafka,
  So that downstream consumers can process telemetry in real-time.

  Scenario Outline: Simulator publishes to Kafka
    When the simulator is running with <count> machines
    Then each machine should publish to Kafka every <interval> seconds
    And the topic should be `iot.sensors.raw`

    Examples:
      | count | interval |
      | 1     | 5        |
      | 10    | 5        |

  Scenario: Kafka messages have correct structure
    When a machine publishes to Kafka
    Then the message key should be the machine_id string
    And the message value should be valid JSON
    And the JSON should contain the same fields as MQTT payload

  Scenario: Messages are partitioned by machine
    When 10 machines publish to Kafka
    Then messages from the same machine should go to the same partition
    And messages from different machines may go to different partitions

  Scenario: Kafka produces with durability guarantees
    When a message is published to Kafka
    Then acks should be set to `all`
    And the message should be persisted before acknowledgment

  Scenario: Kafka handles broker unavailability
    Given the Kafka broker is not reachable
    When the simulator attempts to publish
    Then the simulator should log a broker error
    And the simulator should continue running
    And MQTT publishing should continue unaffected
