SELECT id,
       creator,
       mimetype,
       fname,
       SIZE,
       PUBLIC,
       metadata,
       d,
       da,
       date_format(from_unixtime(unix_timestamp(d)), '%Y-%m-%d %H:%i:%s.%f')
        AS de,
       unix_timestamp(d) - :d + expires AS expires,
       content
FROM bucket
WHERE id=:object_id {}
  AND unix_timestamp(d) + expires >= :d
