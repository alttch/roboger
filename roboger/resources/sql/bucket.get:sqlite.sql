SELECT id,
       creator,
       mimetype,
       fname,
       SIZE,
       PUBLIC,
       metadata,
       d,
       da,
       datetime(strftime('%s', d) + expires, 'unixepoch') AS de,
       strftime('%s', d) - :d + expires AS expires,
       content
FROM bucket
WHERE id=:object_id {}
  AND datetime(strftime('%s', d) + expires, 'unixepoch') >= :d
