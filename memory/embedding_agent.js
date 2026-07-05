'use strict';

const MODEL = 'keyword-frequency';
const DIMENSIONS = 384;

function cleanText(text) {
  return text.toLowerCase()
    .replace(/[^a-zа-яё0-9_]/g, ' ')
    .replace(/[\s]+/g, ' ')
    .trim();
}

function extractTrigrams(text) {
  const cleaned = cleanText(text);
  const trigrams = [];
  for (let i = 0; i + 2 < cleaned.length; i++) {
    trigrams.push(cleaned.substring(i, i + 3));
  }
  return trigrams;
}

function hashToDim(trigram) {
  let h = 0;
  for (let i = 0; i < trigram.length; i++) {
    h = ((h << 5) - h + trigram.charCodeAt(i)) | 0;
  }
  return Math.abs(h) % DIMENSIONS;
}

function textToVector(text) {
  const trigrams = extractTrigrams(text);
  const vec = new Float32Array(DIMENSIONS);

  if (trigrams.length === 0) return vec;

  const countMap = new Map();
  for (const tg of trigrams) {
    countMap.set(tg, (countMap.get(tg) || 0) + 1);
  }

  for (const [tg, count] of countMap) {
    const dim = hashToDim(tg);
    const tf = Math.log1p(count) / Math.log1p(trigrams.length);
    vec[dim] += tf;
  }

  const magnitude = Math.sqrt(vec.reduce((s, v) => s + v * v, 0));
  if (magnitude > 0.0001) {
    for (let i = 0; i < DIMENSIONS; i++) {
      vec[i] /= magnitude;
    }
  }

  return vec;
}

function vectorToBuffer(vec) {
  return Buffer.from(vec.buffer);
}

function bufferToVector(buf) {
  return new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
}

function cosineSimilarity(a, b) {
  let dot = 0;
  for (let i = 0; i < DIMENSIONS; i++) {
    dot += a[i] * b[i];
  }
  return Math.max(-1, Math.min(1, dot));
}

function embed(text) {
  const start = Date.now();
  const single = typeof text === 'string';
  const texts = single ? [text] : text;

  const embeddings = texts.map(t => textToVector(t));
  const timeMs = Date.now() - start;

  return {
    embeddings,
    model: MODEL,
    dimensions: DIMENSIONS,
    tokens_used: texts.reduce((s, t) => s + extractTrigrams(t).length, 0),
    time_ms: timeMs
  };
}

function batchEmbed(texts) {
  return embed(texts);
}

function compare(textA, textB) {
  const [embA, embB] = embed([textA, textB]).embeddings;
  return {
    similarity: cosineSimilarity(embA, embB),
    dimensions: DIMENSIONS,
    model: MODEL
  };
}

function validate(embeddings) {
  if (!Array.isArray(embeddings)) embeddings = [embeddings];

  for (let i = 0; i < embeddings.length; i++) {
    const vec = embeddings[i];
    if (!vec || vec.length !== DIMENSIONS) {
      return { valid: false, error: `Vector ${i}: wrong dimensions, got ${vec ? vec.length : 0}, expected ${DIMENSIONS}` };
    }
    for (let j = 0; j < vec.length; j++) {
      if (!Number.isFinite(vec[j])) {
        return { valid: false, error: `Vector ${i}[${j}]: non-finite value ${vec[j]}` };
      }
    }
    const mag = Math.sqrt(vec.reduce((s, v) => s + v * v, 0));
    if (mag < 0.00001) {
      return { valid: false, error: `Vector ${i}: zero vector` };
    }
  }

  return { valid: true, count: embeddings.length, dimensions: DIMENSIONS, model: MODEL };
}

function embedWithContext(text, type, tags) {
  const enriched = `[type: ${type || 'unknown'}] [tags: ${(tags || []).join(', ')}] ${text}`;
  return embed(enriched);
}

module.exports = {
  embed, batchEmbed, compare, validate, embedWithContext,
  cleanText, extractTrigrams, textToVector, vectorToBuffer, bufferToVector, cosineSimilarity,
  hashToDim,
  MODEL, DIMENSIONS
};
