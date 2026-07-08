# 300 Concurrency Load Test Runbook

## 1. Start local multi-instance API

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\start_multi_instance.py --ports 8001,8002,8003,8004
```

Stop the temporary instances after testing:

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\stop_multi_instance.py --force
```

Start background workers. `WORKER_CONCURRENCY` can also be set in `.env`.

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe -m core.interview_worker --workers 2
```

Process a bounded number of queued jobs and exit:

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe -m core.interview_worker --once --max-jobs 10
```

## 2. Safe tests without cloud quota

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\layered_load_test.py --base-url http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003,http://127.0.0.1:8004 --stage ready --requests 300 --concurrency 300 --timeout 30
```

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\layered_load_test.py --base-url http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003,http://127.0.0.1:8004 --stage home --requests 300 --concurrency 300 --timeout 30
```

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\layered_load_test.py --stage login --passport-no P1234567 --password 123456 --requests 100 --concurrency 20 --timeout 30
```

## 3. Cloud-consuming smoke test

This calls LLM and TTS, so keep the numbers small first.

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\layered_load_test.py --stage start_interview --allow-cloud --requests 5 --concurrency 1 --timeout 90
```

Scale only after confirming Alibaba Cloud ASR/TTS, DashScope, MySQL, Redis, and OSS quotas.
TTS probe traffic only creates local temporary `/media/tts` playback files; OSS is only for final interview recordings.
The legacy WebRTC `/offer` route has been removed. The current interview media path is browser `MediaRecorder` for local recording, WebSocket for realtime ASR, and HTTP upload to OSS for the final recording.

`/health` now includes `capacity` and `worker_queue` snapshots. Use `/ready`
for lightweight load-balancer checks and `/health` for operator checks.

## 4. WebSocket ASR probe

This opens realtime Alibaba Cloud ASR connections. Use `finish_asr` first so the
probe validates ASR without triggering LLM/TTS reply generation.

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\asr_ws_probe.py --allow-cloud --session-id your_session_id --connections 1 --concurrency 1 --action finish_asr
```

Create short-lived sessions automatically only after confirming cloud quota:

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\asr_ws_probe.py --allow-cloud --create-sessions --connections 5 --concurrency 5 --action finish_asr --fallback-text "ASR probe fallback"
```

## 5. Media upload probe

Pass existing live session ids when you only want to test upload behavior:

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\media_upload_probe.py --session-id your_session_id --requests 20 --concurrency 5 --size-bytes 4096
```

Create sessions automatically only for a small cloud-consuming smoke test:

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\media_upload_probe.py --allow-cloud --create-sessions --requests 5 --concurrency 1 --size-bytes 4096
```

Use `--no-cancel-created-sessions` if the same created sessions will be passed
to worker queue testing afterward.

## 6. Worker queue probe

Synthetic mode validates enqueue/idempotency/status visibility without calling
cloud services. It still writes background job rows to the configured database.

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\worker_queue_probe.py --tasks 10 --duplicates 2 --concurrency 5 --poll-timeout 30
```

Full-chain mode creates sessions and uploads fake media before enqueueing, so it
uses LLM/TTS and OSS for the final recording upload only:

```powershell
C:\Users\DELL\anaconda3\envs\torch2\python.exe tools\worker_queue_probe.py --full-chain --allow-cloud --tasks 5 --concurrency 2 --poll-timeout 180
```
