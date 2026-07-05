# Output Filter

## Role
Filters terminal output to extract what matters. Strips noise (escape codes, prompts, command echoes), keeps signal (results, errors, data). Turns a raw terminal transcript into clean, actionable information.

## Contract
- **Receives**: `{ events: [{ type, data }], filters: ["strip_ansi"|"remove_echo"|"remove_prompts"|"remove_empty_lines"|"extract_data"], context: { last_command } }`
- **Returns**: `{ filtered: string, removed: { echo_lines, prompt_lines, empty_lines, ansi_bytes }, extracted: { tables, json_blocks, error_lines, file_paths } }`
- **Side effects**: none (pure filtering)

## Decision Flow

1. **Strip ANSI codes**
   - Delegate to ansi_parser in `strip` mode
   - Remove all escape sequences, colors, cursor movements
   - Preserve content that was styled (the text behind the codes)

2. **Remove command echo**
   - When terminal echoes back the command we just sent
   - Match: `last_command` text at start of output
   - Strip the echoed line (but keep subsequent output from the command)
   - Shell-specific: bash echoes raw, PowerShell formats differently
   - Multi-line commands: strip each line of the echoed command

3. **Remove prompts**
   - Detect and strip: `user@host:~$ `, `PS > `, `%~ `, `>>> `, `... `
   - Multi-line prompts (PS2): `> `, `.. `, `... `
   - Keep: output between prompts (that's the content we want)
   - If strip removes everything → session was all prompt, no output

4. **Remove empty/whitespace-only lines**
   - Remove: blank lines, whitespace-only lines
   - Keep: intentional blank lines in formatted output (heuristic: don't collapse >2 consecutive)

5. **Extract structured data**
   - Tables: ASCII table borders (`+---+`, `| cell |`) → extract as structured rows
   - JSON blocks: `{...}` or `[...]` spanning lines → extract, validate, return
   - Error lines: lines containing error keywords → extract for error_detector
   - File paths: `/path/to/file`, `C:\path\to\file` → extract, validate existence
   - URLs: `https://...` → extract

## Failure Modes
| Condition | Response |
|---|---|
| All content filtered away | Return empty + summary of what was removed |
| Echo removal removes legitimate output | Flag: "echo removal may have removed content" |
| Prompt detection false positive | Flag removed lines, let caller review |
| JSON extraction fails (malformed) | Extract as raw text block, don't attempt parse |
