import assert from 'node:assert/strict';
import { extractTotalScore, parseInterviewReport } from '../frontend/admin/js/report_parser.mjs';

const structuredRecord = {
  evaluation_result: '综合得分：82/100',
  evaluation_result_json: JSON.stringify({
    total_score: 82,
    dimension_scores: [
      { name: '自我介绍与表达', score: 16, comment: '表达清楚' },
      { name: '专业匹配度', score: 17, comment: '基础扎实' }
    ],
    strengths: ['表达清楚'],
    improvements: ['举例可以更具体'],
    summary: '整体较稳定'
  })
};

const legacyRecord = {
  evaluation_result: `综合得分：76/100

各项得分与评价：
- 自我介绍与表达 (15/20)：表达较完整
- 专业匹配度 (16/20)：有一定匹配度

核心优势：
- 表达自然

改进建议：
- 规划还可更具体`,
  evaluation_result_json: ''
};

assert.equal(extractTotalScore(structuredRecord), 82);
assert.equal(parseInterviewReport(structuredRecord).dimensions.length, 2);
assert.equal(extractTotalScore(legacyRecord), 76);
assert.equal(parseInterviewReport(legacyRecord).advantages[0], '表达自然');
