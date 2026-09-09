#Variables
NAME = iot-playground
COMPOSE = docker-compose.yml
GREEN=\033[0;32m
RED=\033[0;31m
RESET=\033[0m

#commands
up:
	docker compose -p $(NAME) -f $(COMPOSE) up --build -d
	echo "$(GREEN)All services started$(RESET)"

#run sensor simulator locally (requires paho-mqtt, confluent-kafka installed)
sensor-run:
	python -m sensors

#run Kafka bridge locally (requires flask, confluent-kafka installed)
bridge-run:
	python -m thingsboard_kafka_bridge

#remove containers
down:
	docker compose -p $(NAME) down
	echo "$(RED)Containers removed$(RESET)"

#remove all data
clean: down
	docker compose -f $(COMPOSE) rm -f
	docker compose -f $(COMPOSE) down --rmi all
	echo "$(RED)All data removed$(RESET)"

#clean stopped containers and free disk
prune: clean
	docker system prune -a --volumes -f
	echo "$(RED)System pruned$(RESET)"
