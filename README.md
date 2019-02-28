What is Roboger?
----------------

* Do you like the old good "echo alarm | sendmail me@mydomain" trick in crontab?
* Does your software or servers send you mail/sms alerts when something is
  wrong?
* Tired of getting emails from robots?

Then Roboger is definitely for you!

Actually nowadays the majority of emails are sent from robots and people don't need to
reply. People eventually use emails much less, preferring messengers and
alternative apps. And we made Roboger - a new generation messenger designed
specifically for robots.

![How Roboger works](roboger-scheme.png?raw=true "How Roboger works")

What can Roboger do?
--------------------

* It can get notifications and forward them to specified endpoints
* It supports endpoint types: email, http/post, http/json, Slack, Telegram and
  Roboger Smartphone App (only via https://roboger.com/)
* This software actually allows you to run your own Roboger server, in case you
  don't want to use https://roboger.com/, want to have a backup alternative or
  want to use custom http web hooks.

Real life example
-----------------

You get information messages from your server to Slack, warnings to Slack and
Telegram, errors to messengers and by mail and on critical events you want to
additionally hook API of your PBX to call you on mobile.

In the past you would have needed to write a code, call APIs, manage event routing and
finish in a script hell without any idea what and where notifies you.

Now you can use Roboger, where everything is already coded, organized and can
be set up with a couple of commands.

How to use
----------

Firstly - set up Roboger server, create address, endpoints and subscriptions
with **./bin/roboger-cmd**

Then use Roboger API to send event notifications:

    POST http://your-roboger-host:7719/push < JSON
    {
        'addr': 'towhere',
        'sender': 'from (e.g. from robot1)',
        'location': 'where something is happened',
        'keywords': 'comma, separated, eg, serverfail, alarm, achtung',
        'subject': 'what we are talking about',
        'msg': 'message body',
        'level': 'alarm level (debug, info, warning, error or critical)',
        'media': 'base64-encoded binary eg. photo from surveillance camera')
    }
    (all fields except address are optional, default level is "info")

Or, for old machines (you can't send binary data with GET):

    GET http://your-roboger-host:7719/push?r=&s=&l=&k=&s=&m=&l=

Or with **roboger-push** console client in the old good crontab or any other
software/scripts:

    echo Everything's down!!! | roboger-push

**roboger-push** app is written in pure bash, so it will run almost everywhere,
addresses are defined in /usr/local/etc/roboger_push.ini.

Note: if you want to send media attachments with roboger-push, you should have
local *openssl* CLI installed (it's actually installed everywhere by default,
we just warn you about that)

Limitations
-----------

* until the launch of https://roboger.com/, stability is very limited, management
  API can be changed at any time. Use at your own risk

Installation
------------

* put roboger to */opt/roboger* (recommended)
* install realpath and pip3
* python3 module python3-cryptography has problems installing via pip3, install
  it rather manually
* run install.sh to make required dirs and install missing python3 mods
* use sqlite database (default) or:
  * install pymysql module (pip3 install pymysql)
  * create mysql database 'roboger' (or set any other name you wish)
  * create mysql user for roboger db
  * run *mysql roboger < roboger-mysql.sql*
* copy etc/roboger.ini.dist to etc/roboger.ini, edit required fields
* obtain Telegram bot token for your private bot if you plan to use
  Telegram endpoints and put it to roboger.ini as well
* run *./sbin/roboger-control start*
* test it: *./bin/roboger-cmd test*
* append '/opt/roboger/sbin/roboger-control start' to /etc/rc.local or any other
  startup place (or use *supervisord*, see below)
* copy *./etc/logrotate.d/roboger* to */etc/logrotate.d/roboger* (not required
  if you run roboger with supervisord)
* that's it :)

Installing roboger-push only
----------------------------

* log in as root
* execute the following command: 

    *curl -s https://raw.githubusercontent.com/alttch/roboger/master/bin/install-roboger-push | bash /dev/stdin YOUR_ROBOGER_ADDRESS*

* customize /usr/local/etc/roboger_push.ini if required

Docker image
------------

* Pre-built image available at https://hub.docker.com/r/altertech/roboger
* Use provided sample *docker-compose.yml* to set initial params

Launching with supervisord
--------------------------

(if working with supervisord, log rotation is not required because roboger
prints everything to stdout)

* install superlance httpok (pip install superlance)
* copy etc/supervisor/conf.d/roboger.conf to /etc/supervisor/conf.d
* put a string to etc/roboger.ini [server] section:

    supervisord_program = roboger

Endpoint types
--------------

* **email** sends email notifications. Config: *rcpt=mail_address* (requires
  SMTP server on localhost or point to the right one in ./etc/roboger.ini)
* **http/post** sends HTTP/POST request. Config: *url=url*, *params=request
  variables (JSON string)*
* **http/json** sends HTTP/POST request with JSON body. Config: *url=url*,
  *params=request_variables (JSON string)*
* **slack** sends notification in Slack. Config: *url=slack_webhook_url*,
  *fmt=rich* (for rich text notifications)
* **telegram** sends notifications in Telegram. Config: *chat_id=your_chat_id*

How it works with Telegram
--------------------------

* Firstly you need to register your own bot and obtain bot token
  (https://core.telegram.org/bots#6-botfather)
* Put bot token to etc/roboger.ini and restart roboger server
* Find your bot in Telegram and write something to chat
* Bot will instantly report you your Chat ID. Use it for *chat_id=chat_id*
  config param when creating endpoint.

Note: roboger Chat ID is different from integer Telegram Chat ID. Actually it's
encrypted with your bot token to avoid people brute forcing chat IDs of shared
bots.

Configuration deployment
------------------------

**./bin/roboger-cmd** does the job, but if you want to deploy in batch, use
*roboger-cmd deploy file.yml* command. Look *sample-deploy.yml* for deployment
example.

