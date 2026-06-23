# Declarative Hash Partitioning for Albums and Album Media Tables

To support user-created static and dynamic albums at scale while keeping all data scoped within their tenant events, the `albums` and `album_media` tables will be declaratively partitioned by `event_id` using hash partitioning (with 64 partitions) from day one.

The primary key of `albums` will be `(event_id, id)`. The `album_media` junction table will use the primary key `(event_id, album_id, media_id)` and define composite foreign keys pointing to both partitioned tables.
