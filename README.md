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

Start Roboger server

```
roboger-control start
# launch in front for debugging
roboger-control launch
```

Then create address, endpoints and subscriptions with
[robogerctl](https://github.com/alttch/robogerctl)

Then use Roboger API to send event notifications:

    POST http://your-roboger-host:7719/push < JSON
    {
        'addr': 'towhere',
        'sender': 'from (e.g. from robot1)',
        'location': 'where something is happened',
        'tag': 'event tag, eg, serverfail, alarm, achtung',
        'subject': 'what we are talking about',
        'msg': 'message body',
        'level': 'event level (debug, info, warning, error or critical)',
        'media': 'base64-encoded binary eg. photo from surveillance camera')
    }
    (all fields except address are optional, default level is "info")

Or with **roboger-push** console client in the old good crontab or any other
software/scripts:

```shell
echo Everything's down!!! | roboger-push -l warning
```

**roboger-push** app is written in pure bash, so it will run almost everywhere,
addresses are defined in /usr/local/etc/roboger_push.ini.

Note: if you want to send media attachments with roboger-push, you should have
local *openssl* CLI installed (it's actually installed everywhere by default,
we just warn you about that)

# Managing

Install robogerctl (not included in server):

```
pip3 install robogerctl
```

# Python client module

Client module for Python 3: https://github.com/alttch/pyrpush. The module can
be installed with pip3:

```
pip3 install pyrpush
```
    
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

Install with pip:

```
pip3 install roboger
```

Get sample configuration file from github repo, put it either to
*/opt/roboger/etc/ or to */usr/local/etc/roboger.yml* or wherever you want and
point there ROBOGER_CONFIG env variable.

Note: Roboger database v2 is not compatible with v1. Please reinstall Roboger
from scratch, for the existing resources use auto-deployment.

## Docker/Kubernetes

* Pre-built image available at https://hub.docker.com/r/altertech/roboger
* Mount server configuration somewhere and point there ROBOGER_CONFIG env
  variable

# Installing roboger-push

* log in as root
* execute the following command: 

    *curl -s https://raw.githubusercontent.com/alttch/roboger/master/bin/install-roboger-push | bash /dev/stdin YOUR_ROBOGER_ADDRESS*

* customize /usr/local/etc/roboger_push.ini if required

# Endpoint plugins

## email

Sends email notifications

endpoint config:

```json
{
  "rcpt" : "some@mail_address"
}
```

server config:

```yaml
- name: email
  config:
    smtp-server: your-smtp-server:port
```

**Note: plugin always requires "sender" field in event push payload.**

## webhook

Sends event web hook HTTP/POST request.

endpoint config:

```json
{
  "url" : "http://some.domain/some-webhook-url",
  "template": "{ "event_id" : $event_id, "name": "value", "name2": "value2" }"
}
```

You may use the following variables in template (quotes for variables are not
required, plugin quotes variables automatically, if necessary):

* **$event_id** event uuid
* **$addr** event recipient address
* **$msg** message text
* **$subject** subject
* **$formatted_subject** pre-formatted extended subject
* **$level** level number (10 = DEBUG, 20 = INFO, 30 = WARNING, 40 = ERROR, 50
  = CRITICAL)
* **$level_name** level name
* **$location** event location (if specified)
* **$tag** event tag (if specified)
* **$sender** event sender (if specified)
* **$media** base64-encoded media, if attached

server config: not required

## chain

Allows to forward event to another Roboger server. Be careful to avoid event
loops!

endpoint config:

```json
{
  "url" : "http://another-roboger-server/push",
  "addr" : "roboger address on target server"
}
```

server config: not required

## slack

Sends notification in Slack.

endpoint config:

```json
{
  "url" : "http://some-slack-web-hook.domain/your-webhook-url",
  "rich": true
}
```

If "rich" is true, rich text notification will be sent. Note that this plugin
doesn't support attachments.

server config: not required

## telegram

sends notifications in Telegram

endpoint config:

```json
{
  "chat_id" : "encrypted chat id, obtained from roboger bot"
}
```

server config:

```yaml
- name: telegram
  config:
    token: your-telegram-bot-token
```

How it works with Telegram:

* Firstly you need to register your own bot and obtain bot token
  (https://core.telegram.org/bots#6-botfather)
* Make sure you have "url" param in "roboger" section of server config.
  Telegram plugin uses this param to process and register web hooks.
* Put bot token to plugin configuration in server config and restart roboger server
* Find your bot in Telegram and write something to chat
* Bot will instantly report your encrypted Chat ID.

Note: roboger Chat ID is different from integer Telegram Chat ID. Actually it's
encrypted with your bot token to avoid people brute forcing chat IDs of shared
bots.

# Server resources-as-a-code

## Single resource

Use *robogerctl <addr|endpoint|subscription> apply -f file.yml* to apply
resource configuration.

## Batch

**robogerctl** does the job, but if you want to deploy in batch, use
*robogerctl deploy -f file.yml* command. Look *sample-deploy.yml* for
deployment example.
