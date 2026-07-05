import assert from 'node:assert/strict';
import { getLatestRecordPerEmail } from '../frontend/admin/js/record_metrics.mjs';

const records = [
  {
    id: 1,
    user_email: '25031212292@stu.xidian.edu.cn',
    session_id: 'old-session',
    created_at: '2026-04-03 08:54:28',
    review_status: '拟录取',
    total_score: 30
  },
  {
    id: 2,
    user_email: '25031212292@stu.xidian.edu.cn',
    session_id: 'latest-session',
    created_at: '2026-04-28 10:14:48',
    review_status: '待复核',
    total_score: 0
  },
  {
    id: 3,
    user_email: 'other@stu.xidian.edu.cn',
    session_id: 'other-session',
    created_at: '2026-04-20 09:00:00',
    review_status: '待复核',
    total_score: 80
  }
];

const latestRecords = getLatestRecordPerEmail(records);

assert.equal(latestRecords.length, 2);
assert.equal(latestRecords[0].session_id, 'latest-session');
assert.equal(latestRecords.find((record) => record.user_email === '25031212292@stu.xidian.edu.cn').total_score, 0);
