# Content Extractor

## Role
Extracts structured content from web responses — HTML scraping, JSON path queries, XML XPath, CSS selectors, regex patterns, and semantic extraction. Answers "get me this specific data from this response."

## Contract
- **Receives**: `{ content: any, content_type: "html"|"json"|"xml"|"text", queries: ExtractorQuery[], options: { trim, dedup, limit } }`
- **Returns**: `{ results: ExtractionResult[], metadata: { sources_used, time_ms, confidence } }`
- **Side effects**: none (pure extraction)

## Decision Flow

1. **Select extraction strategy by content type**
   - HTML: CSS selectors, XPath, semantic selectors (role, aria-label)
   - JSON: JSONPath (`$.store.books[*].author`), JMESPath, jq-style
   - XML: XPath, namespace-aware queries
   - Text: regex with capture groups, line-based extraction (`grep`-style)
   - Hybrid: extract from script tags (JSON-LD, `application/ld+json`), meta tags, microdata

2. **Execute queries**
   - CSS selector: `.product-name`, `#main-content`, `a[href^="/product/"]`
   - JSONPath: `$.data[*].attributes.title`
   - XPath: `//div[@class="price"]/text()`
   - Regex: `Price:\s*\$(\d+\.\d{2})` with named groups
   - Multiple queries: run in parallel, merge results
   - Default value: if query returns nothing, use fallback

3. **Transform and clean**
   - Trim whitespace, collapse newlines
   - HTML decode entities (`&amp;` → `&`, `&#x27;` → `'`)
   - URL resolution: relative paths → absolute URLs
   - Number parsing: strip currency symbols, thousand separators
   - Date parsing: relative ("2 hours ago") → absolute ISO 8601
   - Deduplicate: remove exact duplicates, near-duplicates (95%+ similarity)

4. **Semantic extraction**
   - JSON-LD: parse structured data (Schema.org: Product, Article, Event, Organization)
   - Open Graph: `og:title`, `og:description`, `og:image`, `og:type`
   - Twitter Cards: `twitter:title`, `twitter:description`, `twitter:image`
   - Microdata/RDFa: itemscope, itemtype, itemprop attributes
   - Meta tags: description, keywords, author, robots
   - Canonical URL: `<link rel="canonical" href="...">`

5. **Validate extraction**
   - Pattern check: does result match expected format? (email, phone, URL, date)
   - Required fields: are all requested queries satisfied?
   - Confidence score: heuristic based on selector specificity, match count, data consistency
   - Truncation detection: result hit limit → flag partial extraction
   - Source attribution: which query produced which result

## Failure Modes
| Condition | Response |
|---|---|
| CSS selector returns 0 elements | Return empty with null confidence, suggest alternative selector |
| JSONPath points to missing key | Return null for that query, continue with others |
| HTML is malformed (unclosed tags) | Use lenient parser, report parse warnings, best-effort extraction |
| Content is behind paywall/login | Detect common patterns, report auth required |
| Anti-scraping measures detected | Report detection, suggest official API or rate limiting |
