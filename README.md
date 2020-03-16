# What is Roboger?

* Do you like the old good "echo alarm | sendmail me@mydomain" trick in crontab?
* Does your software or servers send you mail/sms alerts when something is
  wrong?
* Tired of getting emails from robots?

Then Roboger is definitely for you!

Actually nowadays the majority of emails are sent from robots and people don't
need to reply. People eventually use emails much less, preferring messengers
and alternative apps. And we made Roboger - a new generation messenger designed
specifically for robots.

![How Roboger works](roboger-scheme.png?raw=true "How Roboger works")

# What can Roboger do?

* It can get notifications and forward them to specified endpoints
* It supports endpoint types: email, http/post, http/json, Slack, Telegram and
  Roboger Smartphone App (only via https://roboger.com/)
* This software actually allows you to run your own Roboger server, in case you
  don't want to use https://roboger.com/, want to have a backup alternative or
  want to use custom http web hooks.

# Real life example

You get information messages from your server to Slack, warnings to Slack and
Telegram, errors to messengers and by mail and on critical events you want to
additionally hook API of your PBX to call you on mobile.

In the past you would have needed to write a code, call APIs, manage event
routing and finish in a script hell without any idea what and where notifies
you.
  
Now you can use Roboger, where everything is already coded, organized and can
be set up with a couple of commands.

# How to use

Firstly - set up Roboger server, create address, endpoints and subscriptions
with **./bin/roboger-cmd**

Then use Roboger API to send event notifications:

    POST http://your-roboger-host:7719/push < JSON
    {
        'addr': 'towhere',
        'sender': 'from (e.g. from robot1)',
        'location': 'where something is happened',
        'tag': 'event tag, eg, serverfail, alarm, achtung',
        'subject': 'what we are talking about',
        'msg': 'message body',
        'level': 'alarm level (debug, info, warning, error or critical)',
        'media': 'base64-encoded binary eg. photo from surveillance camera')
    }
    (all fields except address are optional, default level is "info")

Or with **roboger-push** console client in the old good crontab or any other
software/scripts:

    echo Everything's down!!! | roboger-push

**roboger-push** app is written in pure bash, so it will run almost everywhere,
addresses are defined in /usr/local/etc/roboger_push.ini.

Note: if you want to send media attachments with roboger-push, you should have
local *openssl* CLI installed (it's actually installed everywhere by default,
we just warn you about that)

# Python client module

Client module for Python 3: https://github.com/alttch/pyrpush. The module can
be installed with pip3:

    pip3 install pyrpush
    
Usage example:
 
```python
from pyrpush import Client as RPushClient

r = RPushClient()
r.sender = 'bot1'
r.location = 'lab'
r.push('test message')
r.push(msg='sending you image', media_file='1.jpg', level='warning')
```

The module requires **roboger-push** client installed (uses its config only, you
can remove *roboger-push* script after the installation)

# Installation

## On the local machine

Install module

```
pip3 install roboger
```

Get sample configuration file from github repo, put it either to
*/opt/roboger/etc/ or to */usr/local/etc/roboger.yml* or wherever you want and
point there ROBOGER_CONFIG env variable.

## Docker/Kubernetes

* Pre-built image available at https://hub.docker.com/r/altertech/roboger
* Mount server configuration somewhere and point there ROBOGER_CONFIG env
  variable

# Installing roboger-push

* log in as root
* execute the following command: 

    *curl -s https://raw.githubusercontent.com/alttch/roboger/master/bin/install-roboger-push | bash /dev/stdin YOUR_ROBOGER_ADDRESS*

* customize /usr/local/etc/roboger_push.ini if required

# Launching with supervisord

(if working with supervisord, log rotation is not required because roboger
prints everything to stdout)

* install superlance httpok (pip install superlance)
* copy etc/supervisor/conf.d/roboger.conf to /etc/supervisor/conf.d
* put a string to etc/roboger.ini [server] section:

    supervisord_program = roboger

# Endpoint plugins

* **email** sends email notifications. Config: *rcpt=mail_address* (requires
  SMTP server on localhost or point to the right one in ./etc/roboger.ini)
* *webhook* sends HTTP/POST request. Config: *url=url*, *template=JSON_template_string*
* **slack** sends notification in Slack. Config: *url=slack_webhook_url*,
  *rich=true* (for rich text notifications)
* **telegram** sends notifications in Telegram. Config: *chat_id=your_chat_id*

# How it works with Telegram

* Firstly you need to register your own bot and obtain bot token
  (https://core.telegram.org/bots#6-botfather)
* Make sure you have "url" param in "roboger" section of server config.
  Telegram plugin uses this param to process and register web hooks.
* Put bot token to plugin configuration in server config and restart roboger server
* Find your bot in Telegram and write something to chat
* Bot will instantly report you your Chat ID. Use it for *chat_id=chat_id*
  config param when creating endpoint.

Note: roboger Chat ID is different from integer Telegram Chat ID. Actually it's
encrypted with your bot token to avoid people brute forcing chat IDs of shared
bots.

# Server resources-as-a-code

## Single resource

Use *roboger-cmd <addr|endpoint|subscription> apply -f file.yml* to apply
resource configuration.

## Batch

**roboger-cmd** does the job, but if you want to deploy in batch, use
*roboger-cmd deploy -f file.yml* command. Look *sample-deploy.yml* for
deployment example.
