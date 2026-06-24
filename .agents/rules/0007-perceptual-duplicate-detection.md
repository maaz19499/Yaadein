# Perceptual Duplicate Detection via pHash

To prevent visually identical or near-duplicate guest uploads (such as compressed copies, watermarked versions, or slightly resized photos) from cluttering event galleries:

1. **Algorithm**: We will use **Perceptual Hashing (pHash)** via a standard 64-bit DCT-based hash (outputting a 64-bit binary sequence).
2. **Database Storage**: The 64-bit pHash will be stored in the `media` table as a `bit(64)` column.
3. **Event Scope**: Duplicate detection is scoped strictly per `event_id` using our partitioned indexes to ensure performance and prevent false positives across unrelated events.
4. **Execution Flow**:
   - After a photo is verified in R2, the Celery background worker computes the 64-bit pHash.
   - The worker runs an XOR-based Hamming distance query inside Postgres:
     `SELECT id FROM media WHERE event_id = :event_id AND bit_count(phash # :new_phash) <= 10`
   - If a duplicate is found (Hamming distance $\le 10$), the new upload's status is set to `rejected` or flagged as a duplicate.
