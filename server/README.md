# Local API Server

Zero-dependency HTTP server wrapping ai-youtube-summary CLI.

## Start
```bash
cd ~/repos/ai-youtube-summary
python3 -m server.api
```

Server runs on http://127.0.0.1:9877 with these endpoints:
- POST /fetch body: {"url":"...","lang":["en"]} -> queue task
- GET /task/{id} -> poll status
- GET /info?url=... -> video info only
- GET /status -> list all tasks
