# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

Please **do not** open a public GitHub Issue for security vulnerabilities.

Email: security@YOUR_DOMAIN (or open a private security advisory on GitHub).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within 72 hours.

## Notes

Æergia∞ v0.1 is a research prototype. The primary security considerations are:

- **Live data source adapters** make outbound HTTP/WebSocket connections.
  Review `aergia/adapters/` if deploying in a restricted network environment.
- **API keys** for NOAA, FRED, GitHub etc. should be passed via environment
  variables, not hard-coded in `.ae` source files.
- The REPL's `:load` command executes arbitrary `.ae` files. Do not run
  untrusted `.ae` files in a privileged environment.
