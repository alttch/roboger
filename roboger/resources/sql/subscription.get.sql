SELECT subscription.id AS id,
       addr.id AS addr_id,
       endpoint_id,
       subscription.active AS active,
       location,
       tag,
       sender,
       level,
       level_match
FROM subscription
JOIN endpoint ON endpoint.id=subscription.endpoint_id
JOIN addr ON addr.id=endpoint.addr_id
WHERE subscription.id=:subscription_id {}
