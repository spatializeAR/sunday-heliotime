.PHONY: help install test lint format clean build deploy-dev deploy-prod check-infra

help:
	@echo "Available commands:"
	@echo "  make install       - Install dependencies"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linting"
	@echo "  make format       - Format code with black"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make build        - Build Lambda deployment package"
	@echo "  make check-infra  - Check AWS infrastructure"
	@echo "  make deploy-dev   - Deploy to development (requires AWS creds)"
	@echo "  make deploy-prod  - Deploy to production (requires AWS creds)"

install:
	pip install -r requirements-dev.txt

test:
	pytest tests/ -v --cov=heliotime --cov-report=term-missing

lint:
	flake8 heliotime/ --max-line-length=120 --ignore=E203,W503
	mypy heliotime/ --ignore-missing-imports

format:
	black heliotime/ tests/ scripts/

clean:
	rm -rf __pycache__ .pytest_cache .coverage
	rm -rf heliotime/__pycache__ tests/__pycache__
	rm -rf lambda_package/ heliotime-lambda.zip
	rm -f infrastructure_report.json
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

build: clean
	mkdir -p lambda_package
	pip install -r requirements.txt -t lambda_package/
	cp -r heliotime/* lambda_package/
	cd lambda_package && zip -r ../heliotime-lambda.zip . -x "*.pyc" -x "*__pycache__*"
	@echo "Lambda package created: heliotime-lambda.zip"

check-infra:
	python scripts/check_infrastructure.py

deploy-dev: build
	@echo "Deploying to development environment..."
	aws lambda update-function-code \
		--function-name heliotime-dev \
		--zip-file fileb://heliotime-lambda.zip \
		--profile SundayDev \
		--publish
	@echo "Development deployment complete"

deploy-prod: build
	@echo "⚠️  WARNING: Deploying to PRODUCTION!"
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	aws lambda update-function-code \
		--function-name heliotime-prod \
		--zip-file fileb://heliotime-lambda.zip \
		--profile SundayDev \
		--publish
	@echo "Production deployment complete"