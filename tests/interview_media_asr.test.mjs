import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dirname = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(dirname, '../frontend/user/js/interview_media.js'), 'utf8');

assert.match(source, /resolveAppUrl\(['"]\/api\/user\/ws\/asr['"]\)/);
assert.doesNotMatch(source, /getAppBasePath\(\)\}\/api\/user\/ws\/asr/);
assert.match(source, /asrError\.code = data\.code/);
assert.match(source, /submitError\.code = data\.code/);
assert.match(source, /error\.code === ['"]asr_empty['"]/);
assert.match(source, /Please speak clearly and answer again/);
assert.match(source, /请靠近麦克风并重新回答/);
