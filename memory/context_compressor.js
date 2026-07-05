'use strict';

const TOKEN_ESTIMATE_PER_CHAR = 0.25;

function countTokens(text) {
  return Math.ceil(text.length * TOKEN_ESTIMATE_PER_CHAR);
}

const MARKERS = {
  decision: /\b(?:decided|decision|chose|choice|selected|opted|agreed|confirmed|resolved)\b/i,
  fact: /\b(?:schema|architecture|convention|pattern|standard|rule|config|version|depends on|requires)\b/i,
  action: /\b(?:ran|executed|deployed|built|created|modified|updated|deleted|moved|migrated|installed|tested)\b/i,
  intent: /\b(?:goal|objective|aim|plan|intend|will|shall|must|need to|going to)\b/i,
  error: /\b(?:error|fail|crash|bug|issue|problem|broken|timeout|exception|rejected|denied)\b/i,
  dependency: /\b(?:blocked by|depends on|requires|prerequisite|needs|waiting for)\b/i
};

const MARKER_LABELS = {
  decision: 'Decision',
  fact: 'Fact',
  action: 'Action',
  intent: 'Intent',
  error: 'Error',
  dependency: 'Dependency'
};

const FILLER_PATTERNS = [
  /^(?:ok|okay|thanks|thank you|got it|understood|sure|alright|fine|great|nice|will do)$/i,
  /^(?:hello|hi|hey|good morning|good afternoon|good evening)/i,
  /^(?:bye|goodbye|see you|talk soon)/i,
  /^\s*$/,
  /^```[\s\S]*?```$/,
  /^\[(?:omit|skipped|truncated)\]/
];

function splitIntoSegments(text) {
  const raw = text.split(/\n\n+/);
  return raw.map((s, i) => ({
    index: i,
    text: s.trim(),
    tokenCount: countTokens(s.trim())
  })).filter(s => s.text.length > 0);
}

function classifySegment(segment) {
  const types = [];
  for (const [type, regex] of Object.entries(MARKERS)) {
    if (regex.test(segment.text)) types.push(type);
  }

  const isFiller = FILLER_PATTERNS.some(p => p.test(segment.text));
  if (isFiller && types.length === 0) types.push('filler');

  return { ...segment, types, isFiller };
}

function extractSalient(content) {
  const segments = splitIntoSegments(content).map(classifySegment);

  const extracted = [];
  let seenFacts = new Set();

  for (const seg of segments) {
    for (const type of seg.types) {
      if (type === 'filler') continue;
      extracted.push({
        type,
        label: MARKER_LABELS[type] || type,
        text: seg.text.slice(0, 500),
        tokens: seg.tokenCount,
        importance: type === 'decision' ? 10 : type === 'error' ? 9 : type === 'intent' ? 7 : type === 'action' ? 6 : type === 'dependency' ? 8 : 4
      });
    }
  }

  return extracted;
}

function compress(content, targetTokens, preserve) {
  const extracted = extractSalient(content);
  const originalTokens = countTokens(content);

  if (extracted.length === 0) {
    return {
      compressed: '',
      original_size: originalTokens,
      compressed_size: 0,
      ratio: 0,
      extracted: [],
      fidelity_estimate: 0
    };
  }

  const preserveSet = new Set(preserve || ['all']);
  const keepAll = preserveSet.has('all');

  let filtered = extracted;
  if (!keepAll) {
    filtered = extracted.filter(e => preserveSet.has(e.type) || preserveSet.has(e.type + 's'));
  }

  filtered.sort((a, b) => b.importance - a.importance);

  const result = [];
  let used = 0;

  for (const item of filtered) {
    if (used + item.tokens > targetTokens && result.length > 0) break;
    result.push(`[${item.label}] ${item.text}`);
    used += item.tokens;
  }

  const allCriticalPreserved = keepAll
    ? extracted.filter(e => e.type === 'decision').every(d => result.some(r => r.includes(d.text.slice(0, 100))))
    : true;

  const coverage = extracted.length > 0 ? result.length / extracted.length : 1;
  const fidelity = coverage * (allCriticalPreserved ? 1 : 0.5);

  return {
    compressed: result.join('\n\n'),
    original_size: originalTokens,
    compressed_size: used,
    ratio: originalTokens > 0 ? used / originalTokens : 0,
    extracted,
    fidelity_estimate: Math.round(fidelity * 100) / 100
  };
}

function process(input) {
  const { content, target_size, preserve, format } = input;
  const result = compress(content, target_size, preserve);

  if (format === 'bullets') {
    result.compressed = result.compressed.replace(/^\[(\w+)\]\s*/gm, '- **[$1]** ');
  } else if (format === 'structured') {
    const structured = {};
    const lines = result.compressed.split('\n\n');
    for (const line of lines) {
      const m = line.match(/^\[(\w+)\]\s*(.*)/);
      if (m) {
        if (!structured[m[1]]) structured[m[1]] = [];
        structured[m[1]].push(m[2]);
      }
    }
    result.structured = structured;
  }

  return result;
}

module.exports = { countTokens, splitIntoSegments, classifySegment, extractSalient, compress, process };
