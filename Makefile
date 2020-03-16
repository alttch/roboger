all:
	@echo "Select target"

test: test-sqlite test-mysql test-postgresql

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
