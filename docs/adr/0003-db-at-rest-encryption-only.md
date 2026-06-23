# Database-Level At-Rest Encryption for PII

To optimize development speed and reduce system complexity pre-PMF, we decided to rely on standard cloud database-level at-rest encryption (provided by Supabase/Postgres) rather than implementing application-side column-level field encryption (such as AES-GCM) for Guest names and face mapping records.

This choice complies with DPDP Act 2023 "reasonable safeguards" while avoiding the overhead of managing KMS/envelope encryption and decryption-on-read in FastAPI middleware.
