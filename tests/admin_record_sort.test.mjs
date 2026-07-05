import assert from 'node:assert/strict';

import { sortRecordsByScore } from '../frontend/admin/js/record_sort.mjs';


const records = [
    { id: 1, evaluation_result_json: JSON.stringify({ total_score: 72 }) },
    { id: 2, evaluation_result: '综合得分：91/100' },
    { id: 3 },
    { id: 4, evaluation_result_json: JSON.stringify({ total_score: 72 }) },
];

assert.deepEqual(sortRecordsByScore(records, 'desc').map(({ id }) => id), [2, 1, 4, 3]);
assert.deepEqual(sortRecordsByScore(records, 'asc').map(({ id }) => id), [1, 4, 2, 3]);
assert.deepEqual(records.map(({ id }) => id), [1, 2, 3, 4]);

console.log('admin record score sorting tests passed');
