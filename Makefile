.PHONY: install run run-api run-watcher run-all docker-build docker-run docker-stop clean

# Установка зависимостей
install:
	pip install -r requirements.txt

# Запуск только API сервера (доступен извне)
run-api:
	python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload

# Запуск только Watcher
run-watcher:
	python run_watcher.py

# Запуск обоих процессов одновременно
run-all:
	python run.py

# Сборка Docker образа
docker-build:
	docker build -t nightwatcher .

# Запуск через Docker Compose
docker-run:
	docker-compose up -d

# Остановка Docker Compose
docker-stop:
	docker-compose down

# Очистка
clean:
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
