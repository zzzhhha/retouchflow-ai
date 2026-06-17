# Release Checklist

Use this checklist before publishing a fork or release archive.

- Run tests: `python -m unittest discover -s local-ai-service/tests`
- Confirm `local-ai-service/config/settings.json` is absent or ignored.
- Confirm `local-ai-service/config/photoshop_actions.json` is absent or ignored.
- Confirm `local-ai-service/runs/` is absent or ignored.
- Confirm no RAW, PSD, Lightroom catalog, proof, or final image files are staged.
- Search for credentials: API keys, relay tokens, bearer tokens, passwords.
- Search for local-only paths such as Windows home directories, temp folders, and custom Photoshop install paths.
- Keep third-party Photoshop Actions out of the repo unless their license permits redistribution.
- Rotate any API key that was ever present in a local working tree.
- Publish as alpha until Photoshop Actions, mask execution, and final export flows are validated across machines.
