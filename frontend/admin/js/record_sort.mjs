import { extractTotalScore } from './report_parser.mjs';


export function sortRecordsByScore(records, order = 'desc') {
    const direction = order === 'asc' ? 1 : -1;
    return records
        .map((record, index) => ({ record, index, score: extractTotalScore(record) }))
        .sort((left, right) => {
            const leftHasScore = Number.isFinite(left.score);
            const rightHasScore = Number.isFinite(right.score);
            if (leftHasScore !== rightHasScore) return leftHasScore ? -1 : 1;
            if (!leftHasScore) return left.index - right.index;
            return (left.score - right.score) * direction || left.index - right.index;
        })
        .map(({ record }) => record);
}
