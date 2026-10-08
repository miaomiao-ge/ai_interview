"""Single-process, bounded volatile state. Never import production persistence."""
import secrets
import time
from dataclasses import dataclass


class PracticeError(Exception):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status


@dataclass
class Session:
    owner: str
    language: str
    expires: float
    turn: int = 0
    busy: bool = False
    speaking: bool = False


class Sessions:
    def __init__(self, capacity=20, ttl=1200, hourly_limit=6, clock=time.monotonic):
        self.capacity, self.ttl, self.hourly_limit = capacity, ttl, hourly_limit
        self.clock = clock
        self.items = {}
        self.starts = {}

    def prune(self):
        now = self.clock()
        for key, value in list(self.items.items()):
            if value.expires <= now:
                del self.items[key]
        for owner, values in list(self.starts.items()):
            recent = [t for t in values if t > now - 3600]
            if recent:
                self.starts[owner] = recent
            else:
                del self.starts[owner]

    def create(self, owner, language):
        self.prune()
        if language not in ('zh', 'en'):
            raise PracticeError('invalid_language')
        if any(s.owner == owner for s in self.items.values()):
            raise PracticeError('already_active', 409)
        if len(self.items) >= self.capacity or len(self.starts) >= 2000:
            raise PracticeError('capacity', 429)
        if len(self.starts.get(owner, [])) >= self.hourly_limit:
            raise PracticeError('rate_limit', 429)
        sid = 'practice_' + secrets.token_urlsafe(24)
        self.items[sid] = Session(owner, language, self.clock() + self.ttl)
        self.starts.setdefault(owner, []).append(self.clock())
        return sid, self.items[sid]

    def get(self, sid, owner):
        self.prune()
        session = self.items.get(sid)
        if not session or session.owner != owner:
            raise PracticeError('session_expired', 404)
        return session

    def finish_answer(self, sid, owner, turn, text):
        session = self.get(sid, owner)
        if session.turn != turn:
            raise PracticeError('stale_turn', 409)
        if not text.strip():
            raise PracticeError('asr_empty')
        session.turn += 1
        if session.turn == 6:
            del self.items[sid]
            return True
        return False

    def delete(self, sid, owner):
        session = self.items.get(sid)
        if session and session.owner == owner:
            del self.items[sid]
