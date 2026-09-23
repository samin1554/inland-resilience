# ADR-008: Authentication

## Status
**Open.** Decision for the lead.

## Context
The spec gives Go "user and session handling" (§6) and a `users` table, but no login method. Rate limits and per-user areas depend on it.

## Options
| Option | Fit |
|---|---|
| **No accounts for MVP** (anonymous session cookie + IP rate limit) | Fastest; enough for demos and evaluation |
| **Magic-link email login** (Go-issued sessions) | Small; matches `users(email)` |
| **Managed auth** (Clerk / Auth0 / Supabase Auth) validated by Go via JWT | Least code; adds a vendor |
| **Google OAuth** | Easy for a university team; ties users to Google |

## Recommendation (non-binding)
Anonymous sessions for Milestones 0–4, then choose before public deployment (Milestone 5). Build the Go middleware so the choice only swaps one component.

## Decision
TBD.
