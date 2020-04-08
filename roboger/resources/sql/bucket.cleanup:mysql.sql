DELETE
FROM bucket
WHERE unix_timestamp(d) + expires < :d
