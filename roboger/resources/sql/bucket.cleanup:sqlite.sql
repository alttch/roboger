DELETE
FROM bucket
WHERE datetime(strftime('%s', d) + expires, 'unixepoch') < :d
