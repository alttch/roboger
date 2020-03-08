__author__ = 'Altertech, http://www.altertech.com/'
__copyright__ = 'Copyright (C) 2018-2020 Altertech Group'
__license__ = 'Apache License 2.0'
__version__ = '1.5.0'

from flask import request, jsonify, Response, abort

import base64
import uuid
import logging

from sqlalchemy import text as sql

success = {'ok': True}

from .core import logger, convert_level, log_traceback, get_app, get_db, send


def push():
    try:
        event_id = str(uuid.uuid4())
        content = request.json
        addr = content.get('addr')
        logger.info(f'API message to {addr}')
        msg = content.get('msg', '')
        subject = content.get('subject', '')
        level = convert_level(content.get('level'))
        location = content.get('location')
        if location == '': location = None
        tag = content.get('tag')
        if tag == '': tag = None
        sender = content.get('sender')
        if sender == '': sender = None
        media_encoded = content.get('media')
        if media_encoded == '': media_encoded = None
        if media_encoded:
            try:
                media = base64.b64decode(media_encoded)
            except:
                media = None
                media_encoded = None
                logger.warning(
                    f'API invalid media file in {event_id} message to {addr}')
        else:
            media = None
        formatted_subject = ''
        level_name = logging.getLevelName(level)
        formatted_subject = level_name
        if location:
            formatted_subject += f' @{location}'
        elif location:
            formatted_subject = location
        if subject: formatted_subject += f': {subject}'
        for row in get_db().execute(sql("""
            SELECT plugin_name, config
            FROM subscription join endpoint ON
                endpoint.id = subscription.endpoint_id
            WHERE addr_id IN (SELECT id FROM addr WHERE a=:addr and active=1)
                AND subscription.active = 1
                AND endpoint.active = 1
                AND (location=:location or location IS null)
                AND (tag=:tag or tag IS null)
                AND (sender=:sender or sender IS null)
                AND (
                    (level_id=:level AND level_match='e') OR
                    (level_id<:level and level_match='g') OR
                    (level_id<=:level and level_match='ge') OR
                    (level_id>:level and level_match='l') OR
                    (level_id>=:level and level_match='le')
                    )
                    """),
                                    addr=addr,
                                    location=location,
                                    tag=tag,
                                    sender=sender,
                                    level=level):
            send(row.plugin_name,
                 event_id=event_id,
                 config=row.config,
                 msg=msg,
                 subject=subject,
                 formatted_subject=formatted_subject,
                 level=level_name,
                 location=location,
                 tag=tag,
                 sender=sender,
                 media=media,
                 media_encoded=media_encoded)
        return success
    except:
        log_traceback()
        abort(503)


def init():
    app = get_app()
    app.add_url_rule('/push', 'push', push, methods=['POST'])
