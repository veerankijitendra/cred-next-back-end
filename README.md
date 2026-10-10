# CredNexa backend

FastAPI API using async SQLAlchemy and Alembic. Copy `.env.example` to `.env` for local development, provide a local database URL, then run the application using the project's normal `uvicorn` entry point.

## Security configuration

`DATABASE_URL` and `JWT_SECRET_KEY` are required. Use a randomly generated signing key with at least 32 bytes; the settings use `SecretStr` and SQLAlchemy SQL echo is disabled. Access tokens last 15 minutes by default (configurable from 1 to 60 minutes). Refresh sessions last 7 days by default (configurable from 1 to 30 days).

Configure `CORS_ALLOWED_ORIGINS` as a comma-separated list of exact frontend origins (scheme and host, with an optional port; no path, wildcard, or substring matching). Development defaults allow Vite at `http://localhost:5173` and `http://127.0.0.1:5173`. In production set `ENVIRONMENT=production`, provide only deployed HTTPS frontend origins, and use `REFRESH_COOKIE_SECURE=true`. Cookie SameSite defaults to `lax`; `none` requires Secure and is intended only for cross-site deployments. Login, refresh, and logout also require an exact trusted `Origin` header.

The built-in authentication rate limiter is bounded and process-local. Enforce equal or stricter limits at a shared gateway in multi-worker or multi-instance deployments. It keys by direct client IP; only use proxy-derived addresses if the trusted proxy configuration is explicit.

## Authentication contract

All paths are under `/api/v1/auth`.

- `POST /register`: JSON `{name,email,phone_number,password}`; returns `201` with `{user_id,reference_id,verification_required,verification_channel}`. Registration creates an unverified account and an OTP record.
- `POST /verify-otp`: JSON `{user_id,channel,otp}`; returns `{success,message}`. OTP is single-use, expires, and has bounded attempts.
- `POST /resend-otp`: JSON `{user_id,channel}`; returns `{success,message}`. Currently no SMS/email provider is configured; it reports `success:false` and does not disclose the OTP. A delivery provider must be integrated before verification can complete in a deployed environment.
- `POST /login`: JSON `{email,password}` and a trusted `Origin`; sets an HttpOnly refresh cookie and returns `{access_token,token_type}`. The refresh credential is not in the response body.
- `POST /refresh`: empty body, trusted `Origin`, and the refresh cookie; rotates the cookie and returns `{access_token,token_type}`. Reuse revokes the token session.
- `POST /logout`: trusted `Origin` and refresh cookie; revokes that one session, clears its cookie, and returns `{success:true,message}`. It is idempotent. It does not revoke other sessions belonging to the user.
- `GET /me`: requires `Authorization: Bearer <access_token>` and returns `{id,name,email,phone_number,role}`.

Every protected request checks that the access JWT is valid and its associated refresh session remains active. Thus logout invalidates access tokens for that session immediately. This incurs a database lookup on authenticated requests. The legacy `users.refresh_token_hash` field is preserved to avoid destructive changes and preserve existing records, but the new session system does not use it. Existing refresh tokens will not work after rollout, and pre-hardening access tokens lack the required claims and must be reissued by signing in.

The frontend currently expects a refresh token in JSON and sends it in the refresh request body. It must set Axios `withCredentials: true`, call refresh with an empty body so the browser sends the HttpOnly cookie, use the returned access token, and call logout before clearing local auth state. It should attempt refresh during startup before treating an in-memory access token absence as logout. No frontend files were changed in this backend task.

## Authorization and business-rule scope

Lead creation requires a valid authenticated user. The authenticated user is the creator and referrer; a client-supplied reference ID cannot attribute a lead to another account. Self/referral classification compares normalized contact numbers to the account phone. The backend has no borrower phone verification flow, so the submitted lead contact cannot be proven to be the borrower's verified phone. There are currently no registered lead list/detail/status routes, admin lead operations, payout calculations, or payout transfers; no commission or Self-Bonus payment is implemented or implied by lead creation.

## Migration and verification

The migration `a7d4c81b2f90` adds refresh-session and refresh-credential tables without deleting existing user or lead data. Review and apply it using the deployment's normal Alembic process before deploying the new application code. Do not run it against production without the normal release approval. The migration invalidates old refresh behavior as described above; existing users and leads are preserved.

Run security unit checks with `python -m unittest discover -s tests -v`. The in-process limiter is only one layer; deployments should configure gateway limits and a real OTP delivery provider. Tests do not establish production security, validate provider configuration, or simulate a PostgreSQL concurrency race.
