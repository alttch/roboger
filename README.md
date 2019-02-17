under development (don't use sqlite engine in production, mysql only)

Installation
------------

* put roboger to /opt/roboger (recommended)
* install realpath and pip3
* python3 modules python3-cryptography and python3-mysqldb have problems
   installing via pip3, install them better manually
* run install.sh to make required dirs and install missing python3 mods
* create mysql database 'roboger' (or set any other name you wish)
* create mysql user for roboger db
* run mysql roboger < roboger.sql
* copy etc/roboger.ini.dist to etc/roboger.ini, edit required fields
* obtain Telegram bot token for your private bot if you plan to use
  Telegram endpoints and put it to roboger.ini as well
* run sbin/roboger-control start
* test it: bin/roboger-cmd test
* append '/opt/roboger/sbin/roboger-control start' to /etc/rc.local or any other
  startup place
* copy etc/logrotate.d/roboger to /etc/logrotate.d/roboger
* that's it :)

Installing roboger-push only
----------------------------

* log in as root
* execute the following command: 
  curl -s https://raw.githubusercontent.com/alttch/roboger/master/bin/install-roboger-push | bash /dev/stdin YOUR_ROBOGER_ADDRESS
* customize /usr/local/etc/roboger_push.ini if required

Launching with supervisord
--------------------------

(if working with supervisord, log rotation is not required because roboger
prints everything to stdout)

* install supervisor-event-listeners (pip install supervisor-event-listeners)
* copy etc/supervisor/conf.d/roboger.conf to /etc/supervisor/conf.d
* put a string to etc/roboger.ini [server] section:

    supervisord_program = roboger

