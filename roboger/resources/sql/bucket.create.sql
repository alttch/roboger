INSERT INTO bucket (id, creator, addr_id, mimetype, fname, size, public,
    metadata, d, expires, content)
VALUES (:object_id, :creator, :addr_id, :mimetype, :fname, :size, :public,
    :metadata, :d, :expires, :content)
