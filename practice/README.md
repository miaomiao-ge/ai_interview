# Independent interview practice

Public path: `/interview/practice/`. Service: `ai-interview-practice`, bound to `127.0.0.1:9010` with **one** Uvicorn worker. Existing formal interview endpoints are not used or changed.

The student signs in normally, then the practice app verifies the existing JWT signature and expiry. It never queries the account database; therefore an already-issued token remains usable until its expiry even if the account is subsequently disabled. No face enrollment or verification is required. Practice never grants formal face-verification status.

## Data contract

- No MySQL, Redis, OSS, scoring, production worker, production session manager, or production router imports.
- Six fixed practice questions per language, independent of the official question bank.
- Camera is a local preview; no complete audio/video recorder or upload API.
- Microphone PCM is streamed to Aliyun for recognition; provider processing still occurs.
- Questions/TTS audio are bounded in-memory caches. Candidate speech and text are not logged or written to disk, browser storage, or a database.
- Sessions expire after 20 minutes; a 15-second sweep removes abandoned sessions. Successful final answer deletes the session. Exit also deletes it; closing a browser is best effort, with expiry as fallback.
- Maximum 20 sessions, 10 active recognizers, 6 starts per student/hour, and 120 seconds/4 MiB per answer. Service restart clears all practice state.
- Text displayed during practice is provisional transcription, not an assessment.

## Installation on the existing server

Use the existing virtualenv dependencies (FastAPI, PyJWT, Aliyun SDK and nls).
Copy `deploy/ai-interview-practice.service` to `/etc/systemd/system/`, then run `systemctl daemon-reload` and `systemctl enable --now ai-interview-practice`.

Include `/opt/ai_interview/deploy/nginx-practice.conf` inside the **HTTPS server block** in `/www/server/panel/vhost/nginx/html_8.137.78.198.conf`. This more-specific location does not inherit the formal interview's response rewriting. Validate using `/www/server/nginx/sbin/nginx -t -c /www/server/nginx/conf/nginx.conf` before reloading the active Nginx.

Add an ordinary link to `/interview/practice/` in the signed-in preparation area of the formal HTML page. Do not import formal `main.js` or `interview_media.js` into practice.

Required environment values: `JWT_SECRET_KEY`, `ALI_AK_ID`, `ALI_AK_SECRET`, `ALI_APPKEY`; optional `ALI_APPKEY_EN`, `JWT_ALGORITHM`, `PRACTICE_ORIGINS`. Systemd reads the existing environment file. Credentials are never committed. Service runs as `www-data`, with a read-only filesystem and no core dumps.

## Checks

```bash
cd /opt/ai_interview
./.venv/bin/python -m pytest -q tests/test_practice.py
curl -fsS http://127.0.0.1:9010/health
curl -fsS https://cryptollm.net/interview/practice/health
systemctl status ai-interview-practice --no-pager
journalctl -u ai-interview-practice -n 50 --no-pager
```

Do not turn on WebSocket frame/debug logging; authentication is sent in the first frame rather than a URL. Error responses carry generic codes, not provider exception bodies.

## Rollback

Remove the practice link and Nginx include, validate and reload Nginx, then stop/disable `ai-interview-practice`. No database migration or data restoration is involved. Existing formal API and worker processes do not require a restart.
