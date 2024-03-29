VERSION=2.0.45

DOCKER_TEST_DB=172.16.99.254
DOCKER_TEST_NETWORK=testnet

all:
	@echo "Select target"

ver:
	find . -not -path "./roboger/plugins/*" -type f -name "*.py" -exec \
			sed -i "s/^__version__ = .*/__version__ = '${VERSION}'/g" {} \;
	find ./bin -type f -exec sed -i "s/^__version__ = .*/__version__ = '${VERSION}'/g" {} \;
	sed -i "s/roboger==.*/roboger==${VERSION}/" Dockerfile

test: update-ctl test-sqlite test-mysql test-postgresql

update-ctl:
	pip3 install -U robogerctl

test-single:
	cd tests && DBCONN=postgresql://roboger:123@localhost/roboger CLEANUP=1 LIMITS=1 pytest -x test.py --log-level DEBUG

test-sqlite:
	cd tests && DBCONN=sqlite:////tmp/roboger-test.db CLEANUP=1 pytest -x test.py --log-level DEBUG
	cd tests && DBCONN=sqlite:////tmp/roboger-test.db CLEANUP=1 LIMITS=1 pytest -x test.py --log-level DEBUG
	rm -f /tmp/roboger-test.db
	sleep 1

test-mysql:
	cd tests && DBCONN=mysql://roboger:123@localhost/roboger CLEANUP=1 pytest -x test.py --log-level DEBUG
	cd tests && DBCONN=mysql://roboger:123@localhost/roboger CLEANUP=1 LIMITS=1 pytest -x test.py --log-level DEBUG
	sleep 1

test-postgresql:
	cd tests && DBCONN=postgresql://roboger:123@localhost/roboger CLEANUP=1 pytest -x test.py --log-level DEBUG
	cd tests && DBCONN=postgresql://roboger:123@localhost/roboger CLEANUP=1 LIMITS=1 pytest -x test.py --log-level DEBUG
	sleep 1

clean:
	rm -rf dist build roboger.egg-info

d: clean test sdist

sdist:
	python3 setup.py sdist

build: clean build-packages

build-packages:
	python3 setup.py build

pub:
	jks build roboger

pub-pypi:
	twine upload dist/*

docker: docker-build docker-test

docker-build:
	docker build -t altertech/roboger:${VERSION}-${BUILD_NUMBER} .
	docker tag altertech/roboger:${VERSION}-${BUILD_NUMBER} altertech/roboger:latest

docker-test:
	docker run --network ${DOCKER_TEST_NETWORK} altertech/roboger:latest env GUNICORN=/opt/venv/bin/gunicorn \
		DBCONN=postgresql://roboger:123@${DOCKER_TEST_DB}/roboger CLEANUP=1 SKIP_BUCKET_TEST=1 \
		/opt/venv/bin/pytest -x /usr/local/roboger-test.py

docker-pub:
	docker push altertech/roboger:${VERSION}-${BUILD_NUMBER}
	docker push altertech/roboger:latest
