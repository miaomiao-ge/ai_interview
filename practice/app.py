"""Practice app: intentionally independent from main, core and production routers."""
import asyncio
import contextlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from practice.sessions import PracticeError, Sessions
from practice.speech import Speech

ROOT = Path(__file__).parent
QUESTIONS = json.loads((ROOT / 'questions.json').read_text(encoding='utf-8'))
sessions = Sessions()
speech = Speech()
tts_slots = asyncio.Semaphore(3)
active_asr = 0


def authenticate(token):
    try:
        payload = jwt.decode(token, os.environ['JWT_SECRET_KEY'],
            algorithms=[os.getenv('JWT_ALGORITHM', 'HS256')], options={'require': ['exp', 'user_id']})
        if not payload.get('passport_no') or not isinstance(payload['user_id'], int):
            raise ValueError('not a student')
        return str(payload['user_id'])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise PracticeError('login_required', 401)


def owner(request):
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        raise PracticeError('login_required', 401)
    return authenticate(header[7:])


def view(sid, session):
    return {'session_id': sid, 'turn': session.turn, 'total': 6,
            'question': QUESTIONS[session.language][session.turn]}


@asynccontextmanager
async def lifespan(app):
    if not os.getenv('JWT_SECRET_KEY'):
        raise RuntimeError('JWT_SECRET_KEY is required')
    async def cleanup():
        while True:
            await asyncio.sleep(15)
            sessions.prune()
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    sessions.items.clear()
    speech.audio.clear()


app = FastAPI(title='Interview practice', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def privacy_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@app.exception_handler(PracticeError)
async def practice_error(request, exc):
    return JSONResponse({'code': exc.code}, status_code=exc.status)


@app.get('/health')
async def health():
    return {'status': 'ok', 'storage': 'memory', 'scoring': False}


@app.get('/')
async def index():
    return FileResponse(ROOT / 'frontend/index.html')


class Start(BaseModel):
    language: str = 'zh'


@app.post('/api/sessions')
async def start(body: Start, request: Request):
    sid, session = sessions.create(owner(request), body.language)
    return view(sid, session)


@app.delete('/api/sessions/{sid}')
async def end(sid: str, request: Request):
    sessions.delete(sid, owner(request))
    return {'ended': True}


@app.get('/api/sessions/{sid}/audio')
async def audio(sid: str, request: Request):
    session = sessions.get(sid, owner(request))
    if session.busy or session.speaking:
        raise PracticeError('capacity', 429)
    session.speaking = True
    try:
        async with tts_slots:
            result = await asyncio.to_thread(speech.synthesize, QUESTIONS[session.language][session.turn], session.language)
        return Response(result, media_type='audio/wav')
    except Exception:
        return JSONResponse({'code': 'tts_unavailable'}, status_code=503)
    finally:
        session.speaking = False


@app.websocket('/api/ws')
async def recognition(ws: WebSocket):
    global active_asr
    expected = os.getenv('PRACTICE_ORIGINS', 'https://cryptollm.net,https://www.cryptollm.net').split(',')
    if ws.headers.get('origin') not in expected:
        await ws.close(code=1008)
        return
    await ws.accept()
    recognizer = sender = session = None
    acquired = False
    try:
        hello = await asyncio.wait_for(ws.receive_json(), 10)
        who = authenticate(hello.get('token', ''))
        sid = hello.get('session_id', '')
        session = sessions.get(sid, who)
        turn = hello.get('turn')
        if turn != session.turn:
            raise PracticeError('stale_turn', 409)
        if session.busy or session.speaking or active_asr >= 10:
            raise PracticeError('capacity', 429)
        session.busy = True
        active_asr += 1
        acquired = True
        queue = asyncio.Queue(maxsize=32)
        recognizer = speech.recognizer(session.language, asyncio.get_running_loop(), queue)
        await asyncio.to_thread(recognizer.start)
        await ws.send_json({'type': 'ready'})

        async def forward():
            while True:
                await ws.send_json(await queue.get())
        sender = asyncio.create_task(forward())
        deadline = asyncio.get_running_loop().time() + 120
        received = 0
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise PracticeError('answer_timeout')
            message = await asyncio.wait_for(ws.receive(), min(remaining, 30))
            if message['type'] == 'websocket.disconnect':
                break
            data = message.get('bytes')
            if data is not None:
                received += len(data)
                if len(data) > 65536 or received > 4 * 1024 * 1024:
                    raise PracticeError('audio_too_large')
                await asyncio.to_thread(recognizer.send, data)
            else:
                action = json.loads(message.get('text') or '{}')
                if action.get('action') != 'finish':
                    raise PracticeError('invalid_action')
                text = await asyncio.to_thread(recognizer.finish)
                sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sender
                completed = sessions.finish_answer(sid, who, turn, text)
                payload = {'type': 'answer', 'text': text, 'completed': completed}
                if not completed:
                    payload.update(view(sid, session))
                await ws.send_json(payload)
                break
    except PracticeError as exc:
        with contextlib.suppress(Exception):
            await ws.send_json({'type': 'error', 'code': exc.code})
    except (asyncio.TimeoutError, WebSocketDisconnect):
        with contextlib.suppress(Exception):
            await ws.send_json({'type': 'error', 'code': 'connection_timeout'})
    except Exception:
        with contextlib.suppress(Exception):
            await ws.send_json({'type': 'error', 'code': 'asr_unavailable'})
    finally:
        # Release in-memory ownership before any cancellable cleanup await.
        if acquired:
            session.busy = False
            active_asr -= 1
        if recognizer:
            recognizer.closed = True
        if sender:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sender
        if recognizer:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(recognizer.stop)
        with contextlib.suppress(Exception):
            await ws.close()


app.mount('/assets', StaticFiles(directory=ROOT / 'frontend'), name='practice-assets')
