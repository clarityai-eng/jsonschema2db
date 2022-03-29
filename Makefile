.DEFAULT_GOAL := precommit

.PHONY: help
help: ## show help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  \033[36m\033[0m\n"} /^[$$()% a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)


.PHONY: install
install:  ## Install project using poetry
	poetry install


.PHONY: lint
lint:  ## Perform linting and formatting
	@echo "Formatting with black"
	@poetry run black .
	@echo "Check for errors with flake8"
	@poetry run flake8 ./


.PHONY: test
test:  ## Run tests
	@poetry run pytest --cov=jsonschema2ddl -v test/


POETRY_EXTRA_ARGS ?=
.PHONY: version
version:  ## Upload a new version to PyPI
	@poetry version $(shell git describe --tags --abbrev=0) && poetry publish --username ${PYPI_USER} --password ${PYPI_PASS} --build $(POETRY_EXTRA_ARGS)


.PHONY: docs
docs:   ## Produce documentation
	@poetry run $(MAKE) -s -C docs clean
	@poetry run $(MAKE) -s -C docs html


.PHONY: clean
clean:  ## Remove build artifacts
	@rm -fr build/
	@rm -fr dist/
	@rm -fr .eggs/
	@find . -name '*.egg-info' -exec rm -fr {} +
	@find . -name '*.egg' -exec rm -f {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +
	@find . -name '__pycache__' -exec rm -fr {} +
	@rm -fr .tox/
	@rm -f .coverage
	@rm -fr htmlcov/
	@rm -fr .pytest_cache
	@$(MAKE) -s -C docs clean


.PHONY: precommit
precommit:  setup clean lint test docs ## Actions befor a commit
