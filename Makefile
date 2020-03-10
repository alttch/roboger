all:
	@echo "Select target"

test:
	cd tests && pytest -x test.py
