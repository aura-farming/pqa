# Secrets discipline
Never load secret material (.env, keys, credentials) into a prompt or a branch. Reference secrets
via environment variables at runtime only. The secrets-guard hook enforces this; do not work around it.
