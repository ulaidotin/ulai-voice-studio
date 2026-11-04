# credentials/

Put the Google Cloud service account key for Gemini here, named exactly:

```
credentials/google-service-account.json
```

Everything in this folder except this README is git-ignored. Docker Compose mounts the folder read-only into the backend at `/app/credentials`. The backend reads the file at startup and sends it to Ulai's hosted agents with each call; it never leaves the server otherwise.

To use a different location, set `GOOGLE_CREDENTIALS_PATH` in `.env`.
