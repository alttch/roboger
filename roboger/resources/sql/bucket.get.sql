SELECT id,
       creator,
       mimetype,
       fname,
       size,
       public,
       metadata,
       d,
       da,
       d + expires AS de,
       d - :d + expires AS expires,
       content
FROM bucket
WHERE id=:object_id {}
  AND d + expires >= :d
