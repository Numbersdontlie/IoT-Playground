#Variables
NAME = IoT
COMPOSE = docker-compose.yml
RED=\033[0;31m
GREEN=\033[0;32
RESET=033[0m

#commands
up:
	docker compose -p $(NAME) - f docker-compose.yml up --build
	echo "$(GREEN)PostgreSQL Db + pgAdmin + Thingsboard created$(RESET)"

#remove host in HOST_URL, also stop and remove containers
down:
	docker compose -p $(NAME) down
	echo "$(RED) (NAME) was removed$(RESET)"

#remove all data
clean: down
	docker compose -f $(COMPOSE) rm -f
	docker compose -f $(COMPOSE) down --rmi all
	echo "$(RED) Directories were removed$(RESET)"

#clean stopped containers
prune: clean
	docker system prune -a --volumes -f