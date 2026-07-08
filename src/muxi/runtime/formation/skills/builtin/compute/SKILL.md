---
name: compute
description: "Use Python execution to compute precise answers when in-context reasoning is unreliable (arithmetic, date math, regex, parsing, data manipulation). Returns a value, not an artifact."
license: Apache-2.0
compatibility: ">=1.0"
allowed-tools: run_skill
---

# Compute

Use Python execution as a reasoning step. Write a small self-contained program,
run it in the sandbox, and read the printed answer back into your reasoning.
The user gets an answer, never code.

## When to activate

- Precise multi-step arithmetic (totals, percentages, compound interest)
- Date and time arithmetic (durations, business days, time zones)
- Regex and structured-text parsing
- Aggregations over more than a handful of rows
- Numerical work (statistics, percentiles, standard deviation)
- Format conversions (encoding, hashing, base conversions)

Do NOT use this skill:

- When a dedicated tool or MCP already answers the question
- For natural-language reasoning, judgment, or writing
- To produce user-facing files (use the `generate_file` tool instead)

## Contract

Write ONE self-contained Python file that:

1. Imports only from the allowed list below.
2. Prints the answer to stdout. Scalar result: print the value directly.
   Structured result: print a single JSON object via `json.dumps`.
   (A trailing bare expression is echoed automatically, REPL-style, but
   prefer an explicit print.)
3. Contains no explanatory comments or prose. The file is code, not narration.
4. Writes no files unless a side-effect artifact is intended (any file created
   in the working directory is auto-registered as an artifact).

## Invocation

Call the `run_skill` tool:

- `skill_name`: `compute`
- `command`: `python3 scripts/run_python.py main.py`
- `input_files`: `{"main.py": "<your Python source>"}`

The result contains `status`, `exit_code`, `stdout`, `stderr`, and
`duration_ms`. Read the answer from `stdout`.

On failure (`status` is not `success`), inspect `stderr`:

- A Python traceback means your code ran and raised. Fix the code and retry.
- `ImportPolicyViolation:` means you used a disallowed import. Rewrite with
  allowed imports only.
- `PathValidationError:` means the file path was rejected. Use a plain
  relative filename such as `main.py`.

Retry at most twice with a fixed or different approach. If it still fails,
report the failure plainly; do not loop.

If stdout looks truncated, rewrite the script to print a compact summary or
write the bulk output to a file (it becomes an artifact) and print only the
key result.

## Allowed imports

Most common: `json`, `math`, `datetime`, `re`, `statistics`, `csv`,
`pandas`, `numpy`.

Also allowed: `scipy`, `statsmodels`, `dateutil`, `decimal`, `fractions`,
`random`, `cmath`, `time`, `calendar`, `zoneinfo`, `collections`,
`itertools`, `functools`, `operator`, `string`, `textwrap`, `unicodedata`,
`io`, `base64`, `hashlib`, `binascii`, `struct`, `uuid`, `heapq`, `bisect`,
`array`.

No networking, no filesystem access outside the working directory, no
subprocesses. Execution is sandboxed with a hard timeout.

## Examples

Worked examples ship with this skill under `references/`:

- `references/arithmetic.md` - compound interest to the cent
- `references/date-math.md` - timezone-aware date arithmetic
- `references/regex-parsing.md` - extracting values from raw text
- `references/data-aggregation.md` - grouped statistics over rows

## Response style

Never show the code, the file path, or sandbox details in your response
unless the user explicitly asks for them. Report the computed answer as a
plain statement, e.g. "The standard deviation is 6.24."
