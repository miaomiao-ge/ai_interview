export function parseStructuredPayload(record) {
    if (!record?.evaluation_result_json) {
        return null;
    }

    try {
        return JSON.parse(record.evaluation_result_json);
    } catch {
        return null;
    }
}

export function extractTotalScore(record) {
    const structured = parseStructuredPayload(record);
    if (structured && Number.isFinite(Number(structured.total_score))) {
        return Number(structured.total_score);
    }

    const text = record?.evaluation_result || '';
    const match = text.match(/(?:综合得分|总分|total score)\s*[:：]?\s*(\d+)/i);
    return match ? Number(match[1]) : null;
}

function parseLegacyTextReport(reportText) {
    if (!reportText) {
        return { dimensions: [], advantages: [], improvements: [], summary: '' };
    }

    const dimensions = [];
    const advantages = [];
    const improvements = [];
    let summary = '';
    let currentSection = '';

    const lines = reportText
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);

    for (const line of lines) {
        if (line.includes('核心优势') || line.toLowerCase().includes('strength')) {
            currentSection = 'advantages';
            continue;
        }
        if (line.includes('改进建议') || line.toLowerCase().includes('improvement')) {
            currentSection = 'improvements';
            continue;
        }
        if (line.startsWith('总结：') || line.startsWith('总结:') || line.toLowerCase().startsWith('summary:')) {
            summary = line.replace(/^(总结[:：]|summary:)\s*/i, '').trim();
            continue;
        }

        const dimMatch = line.match(/^-+\s*(.+?)\s*\((\d+)(?:\/20)?\)\s*[:：]?\s*(.+)$/);
        if (dimMatch) {
            dimensions.push({
                name: dimMatch[1].trim(),
                score: Number(dimMatch[2]),
                comment: dimMatch[3].trim(),
            });
            currentSection = '';
            continue;
        }

        if (line.startsWith('-')) {
            const itemText = line.replace(/^-+\s*/, '').trim();
            if (currentSection === 'advantages') {
                advantages.push(itemText);
            } else if (currentSection === 'improvements') {
                improvements.push(itemText);
            }
        }
    }

    return { dimensions, advantages, improvements, summary };
}

export function parseInterviewReport(record) {
    const structured = parseStructuredPayload(record);
    if (structured) {
        return {
            dimensions: Array.isArray(structured.dimension_scores) ? structured.dimension_scores : [],
            advantages: Array.isArray(structured.strengths) ? structured.strengths : [],
            improvements: Array.isArray(structured.improvements) ? structured.improvements : [],
            summary: structured.summary || '',
        };
    }

    return parseLegacyTextReport(record?.evaluation_result || '');
}
