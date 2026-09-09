Feature: ThingsBoard to Kafka Bridge

  As a data engineer,
  I want ThingsBoard events forwarded to Kafka via a webhook bridge,
  So that streaming consumers can process device telemetry and alarms.

  Scenario: Bridge accepts webhook events from ThingsBoard
    When ThingsBoard sends a POST request to `/events`
    And the body contains telemetry data
    And the header `X-Event-Type` is `telemetry`
    Then the bridge should respond with 202 Accepted
    And the data should be published to `thingsboard.telemetry` Kafka topic

  Scenario: Bridge routes alarm events correctly
    When ThingsBoard sends a POST request to `/events`
    And the body contains alarm data
    And the header `X-Event-Type` is `alarm`
    Then the data should be published to `thingsboard.alarm` Kafka topic

  Scenario: Bridge routes attribute updates correctly
    When ThingsBoard sends a POST request to `/events`
    And the body contains attribute data
    And the header `X-Event-Type` is `attribute_update`
    Then the data should be published to `thingsboard.attributes` Kafka topic

  Scenario: Bridge handles invalid payload
    When ThingsBoard sends a POST request with malformed JSON
    Then the bridge should respond with 400 Bad Request
    And no message should be published to Kafka

  Scenario: Bridge handles Kafka unavailability
    Given the Kafka broker is not reachable
    When the bridge receives a webhook event
    Then the bridge should respond with 503 Service Unavailable
    And the event should not be lost (ThingsBoard will retry)

  Scenario: Bridge exposes health endpoint
    When a health check requests GET `/healthz`
    Then the bridge should respond with 200 OK
    And the response should indicate Kafka connectivity status

  Scenario: End-to-end ThingsBoard to Kafka flow
    Given the bridge is running and Kafka is available
    When a device publishes telemetry to ThingsBoard via MQTT
    And ThingsBoard triggers the webhook rule
    Then the data should appear in `thingsboard.telemetry` Kafka topic
    And the data should arrive within 5 seconds
