PYTHON := python
PIP := pip

lint: ## Run all linting tools
	@echo "Installing linting tools..."
	@$(PIP) install --quiet --upgrade pycln isort ruff
	@echo "Running Ruff checks..."
	@$(PYTHON) -m ruff check --fix --exit-zero
	@echo "Cleaning unused imports..."
	@$(PYTHON) -m pycln .
	@echo "Sorting imports..."
	@$(PYTHON) -m isort .
	@echo "Formatting code..."
	@$(PYTHON) -m ruff format $(SRC_DIR)
	@echo "Linting complete!"

run:
	uvicorn app.main:application --host 0.0.0.0 --port 8885