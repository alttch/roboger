DELETE
FROM bucket
WHERE d + expires < :d
