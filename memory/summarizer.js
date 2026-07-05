'use strict';

const STOP_WORDS_FOR_KEYWORDS = new Set([
  'the', 'a', 'an', 'is', 'of', 'and', 'to', 'in', 'that', 'it', 'for',
  'on', 'with', 'as', 'this', 'was', 'are', 'be', 'has', 'had', 'at',
  'or', 'from', 'by', 'not', 'but', 'can', 'been', 'were', 'they', 'them',
  'their', 'we', 'you', 'i', 'he', 'she', 'do', 'does', 'will', 'would',
  'could', 'should', 'may', 'also', 'if', 'so', 'no', 'all', 'each',
  'every', 'any', 'than', 'then', 'just', 'about', 'into', 'over', 'after',
  'before', 'between', 'under', 'again', 'here', 'there', 'which', 'what',
  'when', 'where', 'who', 'how', 'up', 'out', 'off', 'down', 'very', 'too',
  'more', 'some', 'such', 'only', 'other', 'new', 'most', 'these', 'those',
  'both', 'few', 'much', 'many', 'one', 'two', 'our', 'my', 'your', 'his',
  'her', 'me', 'us', 'him', 'now', 'still', 'well', 'back', 'even', 'own',
  'get', 'got', 'put', 'set', 'see', 'use', 'make', 'made', 'take', 'like',
  'going', 'go', 'went', 'done', 'know', 'need', 'way', 'thing', 'things'
]);

function detectType(text) {
  const lower = text.toLowerCase();
  if (/```|function |const |let |var |import |require\(|export |class |interface |type |def |fn |func /.test(text)) return 'code';
  if (/^\s*\{[\s\S]*\}\s*$/.test(text)) return 'json';
  if (/\b(?:ERROR|WARN|INFO|DEBUG|TRACE|FATAL)\b/.test(text) && /\d{4}-\d{2}-\d{2}/.test(text)) return 'log';
  if (/\b(?:decided|decision|chose|selected|agreed)\b/i.test(text)) return 'decision_record';
  if (/^(?:hi|hello|hey|thanks|bye|ok|okay|sure|got it)/i.test(text.trim()) && text.length < 150) return 'conversation';
  return 'documentation';
}

function extractKeywords(text) {
  const cleaned = text.toLowerCase().replace(/[^a-zа-яё0-9_\s.-]/g, ' ');
  const words = cleaned.split(/[\s]+/);

  const freq = new Map();
  for (const w of words) {
    if (w.length < 3) continue;
    if (w.length > 30) continue;
    if (STOP_WORDS_FOR_KEYWORDS.has(w)) continue;
    if (/^\d+$/.test(w)) continue;
    freq.set(w, (freq.get(w) || 0) + 1);
  }

  const sorted = [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([w]) => w);

  const phrases = extractPhrases(cleaned);

  return [...new Set([...sorted, ...phrases.slice(0, 5)])].slice(0, 10);
}

function extractPhrases(text) {
  const phrases = [];
  const bigramRe = /([a-z]{3,20})\s+([a-z]{3,20})/g;
  let match;
  const counts = new Map();
  while ((match = bigramRe.exec(text)) !== null) {
    const bg = match[1] + '_' + match[2];
    if (STOP_WORDS_FOR_KEYWORDS.has(match[1]) && STOP_WORDS_FOR_KEYWORDS.has(match[2])) continue;
    counts.set(bg, (counts.get(bg) || 0) + 1);
  }
  for (const [phrase, count] of counts) {
    if (count >= 2) phrases.push(phrase.replace('_', ' '));
  }
  return phrases.slice(0, 10);
}

function generateTitle(content) {
  const keywords = extractKeywords(content);
  const type = detectType(content);

  if (keywords.length === 0) return `${type}: Untitled`;

  const prefix = type === 'decision_record' ? 'Decision' :
    type === 'error' ? 'Error' :
    type === 'log' ? 'Log' :
    type === 'conversation' ? 'Note' : 'Entry';

  const core = keywords.slice(0, 3).join(' ');
  const title = `${prefix}: ${core}`;
  return title.slice(0, 100);
}

function generateSummary(content, level) {
  const type = detectType(content);
  const keywords = extractKeywords(content);
  const title = generateTitle(content);

  if (content.length < 50 || level === 'title') {
    return { summary: title, title, keywords, compression_ratio: 1, confidence: 1 };
  }

  let summary;
  let ratio;
  let confidence = 0.8;

  switch (level) {
    case 'oneliner': {
      const firstLine = content.split(/\n\n|\.\s|\n/)[0].trim().slice(0, 200);
      summary = firstLine;
      ratio = content.length > 0 ? summary.length / content.length : 1;
      break;
    }
    case 'short': {
      const sentences = content.split(/[.!?]\s+/);
      const key = sentences.filter(s =>
        keywords.some(kw => s.toLowerCase().includes(kw))
      ).slice(0, 3);
      summary = key.join('. ') + (key.length > 0 ? '.' : content.slice(0, 200));
      if (summary.length > 500) summary = summary.slice(0, 497) + '...';
      ratio = summary.length / content.length;
      break;
    }
    case 'detailed': {
      const lines = content.split('\n');
      const keyLines = lines.filter(l =>
        keywords.some(kw => l.toLowerCase().includes(kw)) || /^\s*[-*#]/.test(l)
      ).slice(0, 15);
      summary = keyLines.join('\n');
      if (summary.length > 2000) summary = summary.slice(0, 1997) + '...';
      ratio = summary.length / content.length;
      confidence = 0.7;
      break;
    }
    default: {
      summary = content.slice(0, 500);
      ratio = summary.length / content.length;
    }
  }

  return {
    summary,
    title,
    keywords,
    compression_ratio: Math.round(ratio * 1000) / 1000,
    confidence
  };
}

function generateEntrySummary(content, options) {
  const level = options.level || 'short';
  const targetLength = options.target_length;
  const focus = options.focus || [];
  let result = generateSummary(content, level);

  if (targetLength && result.summary.length > targetLength) {
    result.summary = result.summary.slice(0, targetLength - 3) + '...';
    result.compression_ratio = result.summary.length / content.length;
  }

  if (focus.length > 0) {
    const focusLower = focus.map(f => f.toLowerCase());
    const sentences = content.split(/[.!?]\s+/);
    const focused = sentences.filter(s => focusLower.some(f => s.toLowerCase().includes(f)));
    if (focused.length > 0) {
      result.summary = '[Focus: ' + focus.join(', ') + '] ' + focused.join('. ');
      if (result.summary.length > 1000) result.summary = result.summary.slice(0, 997) + '...';
    }
  }

  return result;
}

module.exports = {
  detectType, extractKeywords, extractPhrases,
  generateTitle, generateSummary, generateEntrySummary
};
