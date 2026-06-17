# Security Policy

This project runs a local HTTP service and can launch desktop Photoshop through
JSX scripts. Keep it bound to `127.0.0.1` unless you have reviewed the code and
understand the risks of exposing local file paths or automation endpoints.

Do not commit:

- `local-ai-service/config/settings.json`
- API keys, relay tokens, or provider credentials
- Lightroom catalogs, RAW files, proof exports, PSD files, or retouched outputs
- `local-ai-service/runs/`

If you find a vulnerability, open a private advisory or contact the maintainer
before publishing exploit details.
