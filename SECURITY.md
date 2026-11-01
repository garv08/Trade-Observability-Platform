# 🔐 Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | ✅ |

## How TOP is meant to run

TOP is a **single-user local tool**. The server binds to `127.0.0.1` by default and has **no authentication**. Do not expose it to a network or the internet without your own access control, such as a reverse proxy with login.

Outbound requests go only to Yahoo Finance (price history) and Screener.in (fundamentals).

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead, use GitHub's private reporting:

1. Go to **Security → Report a vulnerability** on the [repository page](https://github.com/garv08/Trade-Observability-Platform/security/advisories/new).
2. Describe the issue, how to reproduce it, and its impact.

You can expect an acknowledgement within 7 days. Once a fix is ready, the advisory will credit you unless you prefer otherwise.
