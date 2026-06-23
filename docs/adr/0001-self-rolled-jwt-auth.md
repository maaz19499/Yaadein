# Use self-rolled JWT authentication in FastAPI

To ensure complete database independence and support a future migration to self-hosted Postgres without third-party vendor lock-in, we decided not to use Supabase Auth. Instead, FastAPI will manage user accounts, hash passwords, issue JWTs, and handle session authentication using standard FastAPI Security utilities.
