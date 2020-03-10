#!/bin/sh

cd .. && gunicorn3 -b 0.0.0.0:7719 roboger.server:app --log-level DEBUG
