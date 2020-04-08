SELECT endpoint.id AS id,
       addr_id,
       plugin_name,
       config,
       endpoint.active AS active,
       description
FROM endpoint
JOIN addr ON addr.id=endpoint.addr_id
WHERE addr.id=:addr_id
  OR addr.a=:addr
ORDER BY id
