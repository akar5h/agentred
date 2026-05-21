# Service architecture overview

The platform is three tiers: edge (CDN + WAF), application (FastAPI services
behind an ALB), and data (Postgres primary + two replicas, Redis for cache
and rate limiting, S3 for blobs).

Application services are organised by bounded context, one repo per service.
Inter-service calls use signed JWTs minted by the auth service; no service
trusts another's claims without verifying the signature against the JWKS.

Async work goes through a single RabbitMQ cluster. Each consumer is
idempotent on the message ID — replays are safe.

## What lives where

- `gateway/`       — public ingress, request signing, rate limits
- `auth/`          — login, sessions, JWT minting
- `billing/`       — Stripe webhooks, invoice generation
- `notify/`        — email + push fanout (SendGrid + APNs)
- `analytics/`     — event ingest into ClickHouse

## What we are not

We are not a microservices shop. Splitting a service requires an RFC and a
clear ownership boundary; no service is allowed below ~200 LoC.
