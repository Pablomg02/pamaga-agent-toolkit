# Theme: security

Find ways an attacker, a malicious input or a careless configuration could
compromise confidentiality, integrity or availability.

Look for:
- Injection: SQL, shell, template, path traversal, LDAP, header, log
  injection; unsafe deserialisation; `eval` on external data.
- Authentication and authorisation: missing checks, checks on the wrong
  object (IDOR), privilege escalation, broken session handling.
- Secrets: credentials, tokens or keys in code, config, logs or error
  messages; secrets sent to third parties.
- Input validation at trust boundaries: sizes, types, ranges, file uploads,
  redirects, SSRF.
- Cryptography: home-made crypto, weak algorithms, predictable randomness for
  security purposes, missing TLS verification.
- Web: XSS, CSRF, permissive CORS, missing security headers where the
  project sets them elsewhere.
- Dependencies: newly added packages that are unmaintained, typo-squatted or
  have known vulnerabilities (only if you can verify it).
- Data exposure: personal data in logs, overly broad API responses, debug
  endpoints left enabled.

Do not flag:
- Theoretical issues on code that never receives untrusted input (say why the
  input is or is not trusted).
- Hardening ideas without a plausible attack path; list them as `low` at
  most.
