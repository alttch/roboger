#!/bin/sh

which realpath > /dev/null
if [ $? != 0 ]; then
    echo 'please install realpath'
    exit 1
fi

D=`realpath $0`
cd `dirname ${D}`

which pip3 > /dev/null
if [ $? != 0 ]; then
    echo 'please install pip3'
    exit 1
fi

if [ ! -x ./sbin/check-mods ]; then
    echo "please run in roboger dir!"
    exit 1
fi

echo "Installing Roboger to `pwd`"

echo "Creating dirs"
mkdir -p ./etc || exit 1
chmod 700 ./etc
mkdir -p ./var/db || exit 1
mkdir -p ./log || exit 1

echo "Checking mods"
./sbin/check-mods install || exit 1

if [ ! -f var/db/roboger.db ]; then
    which sqlite3 > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "Creating database ./var/db/roboger.db"
        sqlite3 ./var/db/roboger.db < roboger-sqlite.sql
        chmod 600 ./var/db/roboger.db
    else
        echo "sqlite3 command not found. create database manually"
    fi
else
    echo "Database var/db/roboger.db already exists"
fi

echo
echo "Finished"
