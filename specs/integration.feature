Feature: End-to-End Integration

  As a system operator,
  I want to verify the complete data pipeline works,
  So that I can trust the system for production-like testing.

  Scenario: Full pipeline — simulator to visualization
    Given all Docker services are running
    And the simulator is publishing with 10 machines
    When 60 seconds pass
    Then ThingsBoard UI should show telemetry for 10 devices
    And PostgreSQL should have stored the telemetry records
    And Kafka topic `iot.sensors.raw` should have received messages

  Scenario: Full pipeline — alarm propagation
    Given a machine has been running for simulated 1000 hours
    When a sensor exceeds a critical threshold
    Then an alarm should appear in ThingsBoard UI
    And an alarm event should be published to `thingsboard.alarm` Kafka topic
    And the machine's health score should reflect the alarm

  Scenario: Kafka bridge receives and routes events
    Given ThingsBoard is receiving telemetry from 10 devices
    And the webhook is configured on ThingsBoard
    When devices publish telemetry for 60 seconds
    Then `thingsboard.telemetry` topic should have 120+ messages
    And `thingsboard.alarm` topic should have messages only when thresholds are breached

  Scenario: Data consistency between MQTT and Kafka
    Given the simulator publishes to both MQTT and Kafka
    When a machine publishes a reading at time T
    Then the same reading should appear in both `v1/devices/me/telemetry` and `iot.sensors.raw`
    And the values should match within noise tolerance

  Scenario: Multiple simulator restarts
    Given the simulator is running with 10 machines
    When the simulator process is stopped and restarted
    Then all 10 machines should resume publishing
    And machine ages should persist (no reset to 0)
    And no duplicate telemetry should be sent during restart
