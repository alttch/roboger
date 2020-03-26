#!/bin/sh

curl -H "Content-Type: application/json" \
  -H "X-Auth-Key: ${ROBOGER_MASTERKEY}" \
  -X POST --data '{ "cmd": " cleanup" }' ${ROBOGER_API}/manage/v2/core
