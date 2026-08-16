IMAGE := personal-finance-bot
CONTAINER := personal-finance-bot

.PHONY: build run stop rm test help

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

test: ## Прогнать тесты
	uv run --group dev pytest

build: ## Собрать Docker-образ
	docker build -t $(IMAGE) .

run: build ## Запустить контейнер (нужны .env и credentials.json в корне проекта)
	docker run -d --name $(CONTAINER) \
		--env-file .env \
		-v $(PWD)/credentials.json:/app/credentials.json:ro \
		$(IMAGE)

stop: ## Остановить контейнер
	docker stop $(CONTAINER)

rm: ## Удалить контейнер
	docker rm $(CONTAINER)
