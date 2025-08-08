.PHONY: help install test lint format clean build check-infra deploy-dev deploy-prod cdk-install cdk-synth cdk-diff

help:
	@echo "Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install       - Install Python dependencies"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linting"
	@echo "  make format       - Format code with black"
	@echo "  make clean        - Clean build artifacts"
	@echo ""
	@echo "Infrastructure (CDK):"
	@echo "  make cdk-install  - Install CDK dependencies"
	@echo "  make cdk-synth    - Synthesize CDK stacks"
	@echo "  make cdk-diff     - Show CDK stack differences"
	@echo ""
	@echo "Deployment:"
	@echo "  make build        - Build Lambda deployment package"
	@echo "  make check-infra  - Check AWS infrastructure"
	@echo "  make deploy-dev   - Deploy to development"
	@echo "  make deploy-prod  - Deploy to production"

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
	python scripts/check_infrastructure_v2.py

cdk-install:
	cd infrastructure && npm install
	npm install -g aws-cdk || true

cdk-synth: cdk-install
	cd infrastructure && npm run build && cdk synth --profile SundayDev

cdk-diff: cdk-install
	cd infrastructure && npm run build && cdk diff --all --profile SundayDev

deploy-dev:
	./scripts/deploy.sh deploy-all dev

deploy-prod:
	./scripts/deploy.sh deploy-all prod