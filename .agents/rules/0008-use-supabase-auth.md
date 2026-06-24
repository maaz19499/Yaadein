# Use Supabase Auth for User Authentication

**Status**: Accepted (Supersedes ADR 0001)

We decided to use **Supabase Auth** (GoTrue) for user authentication, signup, signin, password resets, and session management, reversing our previous decision to use a self-rolled JWT authentication system in FastAPI.

### Rationale
Using Supabase Auth significantly reduces development time and operational complexity, providing social logins, email verification, and built-in session handlers out of the box. Because Supabase Auth maps directly to Postgres RLS policies (using `auth.uid()`), this design simplifies secure tenant boundaries for our database operations.

Our public `users` table will now reference the `auth.users` table managed by Supabase, and we will no longer manage password hashing or custom JWT token generation inside FastAPI.
