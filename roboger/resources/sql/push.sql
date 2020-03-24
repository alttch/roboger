SELECT plugin_name, config, addr.id as addr_id
FROM subscription JOIN endpoint ON
    endpoint.id = subscription.endpoint_id JOIN addr ON
    endpoint.addr_id = addr.id WHERE
    addr.a=:a
    AND addr.active=1
    AND subscription.active = 1
    AND endpoint.active = 1
    AND (location=:location or location IS null)
    AND (tag=:tag or tag IS null)
    AND (sender=:sender or sender IS null)
    AND (
        (level=:level AND level_match='e') OR
        (level<:level and level_match='g') OR
        (level<=:level and level_match='ge') OR
        (level>:level and level_match='l') OR
        (level>=:level and level_match='le')
        )
