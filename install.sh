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
mkdir -p ./var || exit 1
mkdir -p ./log || exit 1

echo "Checking mods"
./sbin/check-mods install || exit 1

echo "Finished"
