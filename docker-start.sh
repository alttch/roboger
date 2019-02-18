#!/bin/bash

if [ $$ -ne 1 ]; then
    echo "This is Docker container startup script"
    exit 99
fi

function _term {
    kill `cat /var/run/supervisord.pid`
}

if [ ! -f /.installed ] || [ ! -f /opt/roboger/etc/roboger.ini ]; then
    cd /opt/roboger
    if [ -d /config ]; then
        rm -rf ./etc
        ln -sf /config etc
    else
        [ ! -d etc ] && mkdir etc
    fi
    if [ -d /db ]; then
        rm -rf ./var/db
        ln -sf /db ./var/db
    else
        [ ! -d var/db ] && mkdir var/db
    fi
    if [ ! -f ./etc/roboger.ini ]; then
        # prepare config
        [ ${masterkey} ] && K=${masterkey} || K=demo123
        touch ./etc/roboger.ini
        chmod 600 ./etc/roboger.ini
        sed "s/VERYSECRETKEY/${K}/g" ./roboger.ini-dist | \
                sed 's/^;supervisord_/supervisord_/g' > ./etc/roboger.ini
        [ ${smtp_host} ] && sed -i "s/^smtp_host.*/smtp_host = ${smtp_host}/g" ./etc/roboger.ini
        [ ${masterkey} ] && sed -i "s/^master_allow.*/master_allow = 0.0.0.0\/0/g" ./etc/roboger.ini 
    fi
    if  [ ! -f ./var/db/roboger.db ]; then
        touch ./var/db/roboger.db
        chmod 600 ./var/db/roboger.db
        cat ./roboger.init.db > ./var/db/roboger.db
    fi
    touch /.installed
fi

if [ -f /.installed  ]; then
    trap _term SIGTERM
    supervisord -n &
    wait $!
else
    exit 10
fi
