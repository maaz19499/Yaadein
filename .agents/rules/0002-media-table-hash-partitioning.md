# Declarative Hash Partitioning for the Media Table

To support high concurrent media queries and scale seamlessly to 10,000+ events per month, the `media` table will be declaratively partitioned by `event_id` using hash partitioning (with 64 partitions) from day one. 

Because Postgres unique constraints on partitioned tables must include the partition key, the primary key for the `media` table will be the composite key `(event_id, media_id)`. All dependent tables (e.g., `comments`, `reactions`) referencing the `media` table must also reference this composite key.
