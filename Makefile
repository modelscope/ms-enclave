# default rule
default: install

.PHONY: docs
docs:
	$(MAKE) docs-en
	$(MAKE) docs-zh

.PHONY: docs-en
docs-en:
	cd docs/en && python -m mkdocs build --clean

.PHONY: docs-zh
docs-zh:
	cd docs/zh && python -m mkdocs build --clean

.PHONY: lint
lint:
	pre-commit run --all-files

.PHONY: dev
dev:
	pip install -e '.[docker,docs]'
	pip install pre-commit

.PHONY: install
install:
	pip install -e .
