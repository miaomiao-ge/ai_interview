function getRecordTime(record = {}) {
    const rawTime = String(record.created_at || '').trim();
    const timestamp = rawTime ? Date.parse(rawTime.replace(' ', 'T')) : NaN;
    return Number.isFinite(timestamp) ? timestamp : 0;
}

function getRecordOrder(record = {}) {
    const id = Number(record.id);
    return Number.isFinite(id) ? id : 0;
}

function getRecordIdentity(record = {}, index = 0) {
    const email = String(record.user_email || '').trim().toLowerCase();
    if (email) {
        return `email:${email}`;
    }

    const sessionId = String(record.session_id || '').trim();
    if (sessionId) {
        return `session:${sessionId}`;
    }

    return `row:${index}`;
}

function isNewerRecord(candidate = {}, current = {}) {
    const candidateTime = getRecordTime(candidate);
    const currentTime = getRecordTime(current);
    if (candidateTime !== currentTime) {
        return candidateTime > currentTime;
    }
    return getRecordOrder(candidate) > getRecordOrder(current);
}

export function getLatestRecordPerEmail(records = []) {
    const latestByIdentity = new Map();

    records.forEach((record, index) => {
        const identity = getRecordIdentity(record, index);
        const current = latestByIdentity.get(identity);
        if (!current || isNewerRecord(record, current)) {
            latestByIdentity.set(identity, record);
        }
    });

    return Array.from(latestByIdentity.values()).sort((left, right) => {
        const timeDiff = getRecordTime(right) - getRecordTime(left);
        if (timeDiff !== 0) {
            return timeDiff;
        }
        return getRecordOrder(right) - getRecordOrder(left);
    });
}
