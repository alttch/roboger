SELECT id,
       addr_id,
       plugin_name,
       config,
       active,
       description
FROM endpoint
WHERE id=:id
