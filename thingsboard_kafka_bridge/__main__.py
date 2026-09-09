"""Entry point for running Kafka bridge directly."""
import logging
import os

from thingsboard_kafka_bridge.webhook_server import WebhookServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def main():
    port = int(os.getenv("BRIDGE_PORT", "8086"))
    kafka_broker = os.getenv("KAFKA_BROKER", "localhost:9092")

    host = "0.0.0.0"
    server = WebhookServer(
        host=host,
        port=port,
        bootstrap_servers=kafka_broker,
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting bridge on %s:%d", host, port)
    server.app.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    main()
