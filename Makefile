VERSION=2.0.2

all:
	@echo "Select target"

ver:
	find . -type f -name "*.py" -exec sed -i "s/^__version__ = .*/__version__ = '${VERSION}'/g" {} \;
	find ./bin -type f -exec sed -i "s/^__version__ = .*/__version__ = '${VERSION}'/g" {} \;

test: test-sqlite test-mysql test-postgresql

test-single:
	cd tests && DBCONN=postgresql://roboger:123@localhost/roboger CLEANUP=1 LIMITS=1 pytest -x test.py --log-level DEBUG

test-sqlite:
	cd tests && DBCONN=sqlite:////tmp/roboger-test.db CLEANUP=1 pytest -x test.py --log-level DEBUG
	cd tests && DBCONN=sqlite:////tmp/roboger-test.db CLEANUP=1 LIMITS=1 pytest -x test.py --log-level DEBUG
	rm -f /tmp/roboger-test.db

test-mysql:
	cd tests && DBCONN=mysql://roboger:123@localhost/roboger CLEANUP=1 pytest -x test.py --log-level DEBUG
	cd tests && DBCONN=mysql://roboger:123@localhost/roboger CLEANUP=1 LIMITS=1 pytest -x test.py --log-level DEBUG

test-postgresql:
	cd tests && DBCONN=postgresql://roboger:123@localhost/roboger CLEANUP=1 pytest -x test.py --log-level DEBUG
	cd tests && DBCONN=postgresql://roboger:123@localhost/roboger CLEANUP=1 LIMITS=1 pytest -x test.py --log-level DEBUG

clean:
	rm -rf dist build roboger.egg-info

d: clean test sdist

sdist:
	python3 setup.py sdist

build: clean build-packages

build-packages:
	python3 setup.py build

pub:
	@echo "please use jenkins to build"

pub-pypi:
	twine upload dist/*
