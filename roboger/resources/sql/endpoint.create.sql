INSERT INTO endpoint (addr_id, plugin_name, config, description)
VALUES (
  (SELECT id FROM addr WHERE id=:addr_id OR a=:addr),
  :plugin, :config, :description)
