# What is Roboger?

* Do you like the old good "echo alarm | sendmail me@mydomain" trick in crontab?
* Does your software or servers send you mail/sms alerts when something is
  wrong?
* Want to build own notification bot for Telegram, Slack or whatever else?
* Tired of getting emails from robots?

Then Roboger is definitely for you!

Actually nowadays the majority of emails are sent from robots and people don't
need to reply. People eventually use emails much less, preferring messengers
and alternative apps. And we made Roboger - a new generation messenger designed
specifically for robots.

![How Roboger works](roboger-scheme.png?raw=true "How Roboger works")

# What can Roboger do?

* It can get notifications and forward them to specified endpoints
* It supports endpoint types: email, JSON webhooks, Slack, Telegram and
  Roboger Smartphone App (only via https://roboger.com/)
* It can be easily extended with endpoint plugins
* This software actually allows you to run your own Roboger server, in case you
  don't want to use https://roboger.com/, want to have a backup alternative

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
[robogerctl](https://github.com/alttch/robogerctl):

```
> robogerctl address create
attr    value
--------------------------------------------------------------------------
res     9                                                                <<< address resource id
a       5VpTb3jp8yUd138saNnOVDkcTPQBDM9k4kpas2QQW6vZyYr19PvXofmHAfTrkm77 <<< your address
active  1

# let's craate endpoint for slack
> robogerctl endpoint create 9 slack
attr         value
--------------------
res          9.7     <<< endpoint resource id
active       1
config       {}
description
plugin_name  slack

# lets create one subscription for this endpoint
> robogerctl subscription create 9.7
attr         value
---------------------
res          9.7.16
active       1
endpoint_id  7
level        20
level_match  ge
location
sender
tag
# edit endpoint configuration
> robogerctl endpoint edit 9.7
```
make sure it looks like

```yaml
active: 1
config:
  url: http://slack-web-hook/url
description: some my chat
```

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
        'media': 'base64-encoded binary eg. photo from surveillance camera',
        'media_file': 'media file name'
    }
    (all fields except address are optional, default level is "info")

Or with **roboger-push** console client in the old good crontab or any other
software/scripts:

```
echo Everything is down | roboger-push -l warning
```

**roboger-push** app is written in pure bash, so it will run almost everywhere,
addresses are defined in /usr/local/etc/roboger_push.ini.

Note: if you want to send media attachments with roboger-push, you should have
local *openssl* CLI installed (it's actually installed everywhere by default,
we just warn you about that)

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
pip3 install gunicorn # if not installed
```

Get sample configuration file from github repo, put it either to
*/opt/roboger/etc/* or to */usr/local/etc/roboger.yml* or wherever you want and
point there ROBOGER_CONFIG env variable.

Note: Roboger database v2 is not compatible with v1. Please reinstall Roboger
from scratch, for the existing resources use auto-deployment.

Roboger can work with SQLite, MySQL and PostgreSQL, however SQLite is not
recommended for production due to possible database locks.

## Docker/Kubernetes

* Pre-built image available at https://hub.docker.com/r/altertech/roboger
* Mount server configuration somewhere and point there ROBOGER_CONFIG env
  variable

# Installing roboger-push

* log in as root
* execute the following command: 

    *curl -s https://raw.githubusercontent.com/alttch/roboger/master/bin/install-roboger-push | bash /dev/stdin YOUR_ROBOGER_ADDRESS*

* customize /usr/local/etc/roboger_push.ini if required

# Managing

Install robogerctl (not included in server):

```
pip3 install robogerctl
```

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
    default-location: location # if not specified, host name is used
```

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

## shell

Executes server command, specified in endpoint configuration. The command is
executed with the user permissions of Roboger server process. Should be enabled
only in trusted environments, where regular users have no direct access to
the endpoint configuration.

endpoint config:

```json
{
  "command" : "server shell command"
}
```

Variables: same as in webhook plugin. Variables are sent to command without
quotes.

## chain

Allows to forward event to another Roboger server. Be careful to avoid event
loops!

endpoint config:

```json
{
  "url" : "http://another-roboger-server",
  "addr" : "roboger address on target server"
}
```

Note: */push* uri is not required in "url" field.

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

If you want to deploy in batch, use *robogerctl deploy -f file.yml* command.
Look *sample-deploy.yml* for deployment example.

## API documentation

Swagger API docs are at http://your-roboger-host:7719/
