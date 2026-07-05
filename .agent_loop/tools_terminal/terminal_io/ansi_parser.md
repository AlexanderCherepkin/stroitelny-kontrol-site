# ANSI Parser

## Role
Parses ANSI escape sequences in terminal output. Converts raw control codes into semantic meaning — colors, cursor movements, screen erases, prompt markers. Without this, terminal output is unreadable noise.

## Contract
- **Receives**: `{ raw_output: string, mode: "strip"|"parse"|"highlight" }`
- **Returns**: `{ clean_text: string, segments: [{ text, attrs: { fg, bg, bold, italic, underline } }], detected: { prompts, errors, progress_bars, links } }`
- **Side effects**: none (pure parsing)

## Decision Flow

1. **Parse SGR (Select Graphic Rendition) — colors and styles**
   - `\x1b[31m` → red foreground, `\x1b[1m` → bold, `\x1b[0m` → reset
   - 256 color: `\x1b[38;5;Nm` → color N from palette
   - True color: `\x1b[38;2;R;G;Bm` → RGB color
   - Build attribute spans: [{text, fg, bg, bold, italic, underline}]

2. **Parse cursor movements**
   - `\x1b[nA` → up N lines, `\x1b[nB` → down, `\x1b[nC` → forward, `\x1b[nD` → back
   - `\x1b[nG` → column N, `\x1b[n;mH` → row N, col M
   - Track virtual cursor → detect overwrites (progress bars, spinners)
   - Detect: cursor up + new text = progress update (don't show as new line)

3. **Parse screen operations**
   - `\x1b[2J` → clear screen, `\x1b[K` → clear line
   - `\x1b[?25l` → hide cursor, `\x1b[?25h` → show cursor
   - Alternate screen: `\x1b[?1049h` (enter), `\x1b[?1049l` (exit)

4. **Output modes**
   - `strip`: remove all ANSI codes, return plain text only. For log analysis.
   - `parse`: return text + attribute spans. For rich rendering.
   - `highlight`: strip codes but add markers for detected elements (prompts, errors, links).

5. **Semantic detection**
   - Prompts: text after last newline + ANSI reset → `detected.prompts`
   - Error indicators: red text, "error"/"failed"/"fatal" keywords → `detected.errors`
   - Progress: repetitive cursor-up patterns → `detected.progress_bars`
   - Links: `https?://...` sequences + OSC 8 hyperlinks → `detected.links`

## Failure Modes
| Condition | Response |
|---|---|
| Malformed ANSI sequence | Treat as literal text (don't strip the `\x1b[`), flag |
| Incomplete sequence at buffer end | Hold in partial buffer, complete on next read |
| Unknown SGR code | Ignore that code, continue parsing |
| Nested CSI sequences | Parse innermost first, warn about nesting |
