# Response Formats - Troubleshooting Guide

Common issues and solutions when working with MUXI Runtime response formats, based on real-world usage and e2e test scenarios.

## Configuration Issues

### Issue: Format Not Applying

**Symptoms:**
- Response always comes back in default format (Markdown)
- Runtime override not working
- Format set in formation.afs ignored

**Common Causes:**

#### 1. Format Set After Chat Call
```python
# ❌ Wrong: Format set after calling chat
response = await overlord.chat("Hello")
overlord.response_format = "json"  # Too late!
```

```python
# ✅ Correct: Format set before calling chat
overlord.response_format = "json"
response = await overlord.chat("Hello")
```

#### 2. Wrong YAML Location
```yaml
# ❌ Wrong: Format not in response block
overlord:
  format: "json"
```

```yaml
# ✅ Correct: Format in response block
overlord:
  response:
    format: "json"
```

#### 3. Invalid Format Name
```python
# ❌ Wrong: Invalid format name
overlord.response_format = "xml"  # Not supported
```

```python
# ✅ Correct: Valid format name
overlord.response_format = "json"  # One of: json, markdown, html, text
```

#### 4. Overlord Instance Not Updated
```python
# ❌ Wrong: Setting on wrong overlord instance
old_overlord = overlord
overlord = await formation.start_overlord()
old_overlord.response_format = "json"  # Wrong instance!
```

```python
# ✅ Correct: Setting on current overlord instance
overlord = await formation.start_overlord()
overlord.response_format = "json"
```

**Solution Checklist:**
- [ ] Format set before calling `overlord.chat()`?
- [ ] Using valid format name (json/markdown/html/text)?
- [ ] Format in correct YAML location (`overlord.response.format`)?
- [ ] Setting format on correct overlord instance?

---

## JSON Format Issues

### Issue: Invalid JSON Response

**Symptoms:**
```python
json.loads(response.content)  # Raises JSONDecodeError
```

**Diagnosis:**
```python
import json

overlord.response_format = "json"
response = await overlord.chat("Test")

# Check what you're parsing
print(f"Type: {type(response.content)}")
print(f"Content: {response.content[:200]}")

# Try parsing
try:
    data = json.loads(response.content)
    print("✅ Valid JSON")
except json.JSONDecodeError as e:
    print(f"❌ Invalid JSON: {e}")
```

**Common Causes:**

#### 1. Parsing Wrong Object
```python
# ❌ Wrong: Trying to parse response object
data = json.loads(response)  # response is ChatResponse object
```

```python
# ✅ Correct: Parse response.content string
data = json.loads(response.content)
```

#### 2. Format Not Actually Set
```python
# ❌ Wrong: Format defaulted to markdown
# (no format set, defaults to markdown which isn't JSON)
response = await overlord.chat("Test")
data = json.loads(response.content)  # Fails - content is markdown
```

```python
# ✅ Correct: Explicitly set JSON format
overlord.response_format = "json"
response = await overlord.chat("Test")
data = json.loads(response.content)  # Works
```

**Solution:**
JSON format is automatically validated and wrapped. If you're getting invalid JSON, check:
1. Format is actually set to "json" before the call
2. You're accessing `response.content`, not `response`
3. Content is a string, not bytes

**Validation:**
```python
def validate_json_response(response):
    """Validate JSON response has required structure."""
    try:
        data = json.loads(response.content)

        # Check required fields
        required = ["content", "type", "format"]
        missing = [f for f in required if f not in data]

        if missing:
            print(f"❌ Missing fields: {missing}")
            return False

        # Check field values
        if data["type"] != "response":
            print(f"❌ Wrong type: {data['type']}")
            return False

        if data["format"] != "json":
            print(f"❌ Wrong format: {data['format']}")
            return False

        print("✅ Valid JSON response")
        return True

    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        return False
```

---

## Markdown Format Issues

### Issue: No Formatting in Response

**Symptoms:**
- Response looks like plain text
- No headers, code blocks, or lists
- Inconsistent formatting

**Diagnosis:**
```python
import re

overlord.response_format = "markdown"
response = await overlord.chat("Create documentation")

# Check for markdown elements
has_headers = bool(re.search(r"^#{1,6}\s+", response.content, re.MULTILINE))
has_code = "```" in response.content or "`" in response.content
has_lists = bool(re.search(r"^\s*[-*+]\s+", response.content, re.MULTILINE))

print(f"Headers: {has_headers}")
print(f"Code blocks: {has_code}")
print(f"Lists: {has_lists}")
```

**Common Causes:**

#### 1. Vague Prompts
```python
# ❌ Vague: LLM may not use formatting
response = await overlord.chat("Tell me about cloud computing")
# Result: Plain paragraph
```

```python
# ✅ Specific: Request specific formatting
response = await overlord.chat(
    "Create documentation for cloud computing with headers, "
    "code examples, and a bullet list of benefits"
)
# Result: Proper markdown structure
```

#### 2. LLM Model Limitations
Some models are better at formatting than others. Check your formation:

```yaml
llm:
  models:
    - text: "openai/gpt-4o-mini"  # Good at formatting
    # vs
    - text: "some-model/tiny"     # May not follow formatting well
```

**Solution:**
Markdown format relies on LLM following instructions. Improve results by:
1. Using more specific prompts mentioning desired structure
2. Requesting specific markdown elements (headers, code blocks, etc.)
3. Using LLM models known for good formatting
4. Consider HTML format if you need guaranteed structure

**Expected Structure Score:**
Markdown should score ≥2 based on presence of:
- Headers (`#`, `##`, `###`) = 1 point
- Code blocks (` ``` `) = 1 point
- Lists (`-`, `*`, `1.`) = 1 point
- Links (`[text](url)`) = 1 point
- Emphasis (`**bold**`, `*italic*`) = 1 point

---

## HTML Format Issues

### Issue: Malformed HTML Tags

**Symptoms:**
- Unclosed tags
- Invalid nesting
- Missing semantic structure

**Diagnosis:**
```python
from bs4 import BeautifulSoup
import re

overlord.response_format = "html"
response = await overlord.chat("Create a webpage")

# Check HTML validity
has_tags = bool(re.search(r"<[^>]+>", response.content))
print(f"Has HTML tags: {has_tags}")

# Parse with BeautifulSoup
try:
    soup = BeautifulSoup(response.content, 'html.parser')
    tags = soup.find_all()
    print(f"✅ Valid HTML with {len(tags)} tags")

    # Check for semantic tags
    semantic = ['h1', 'h2', 'h3', 'p', 'ul', 'li']
    found = [tag.name for tag in tags if tag.name in semantic]
    print(f"Semantic tags: {set(found)}")

except Exception as e:
    print(f"❌ HTML parsing error: {e}")
```

**Common Causes:**

#### 1. LLM Not Closing Tags
HTML format uses BeautifulSoup to automatically fix this, but severe issues may remain.

```python
# If BeautifulSoup can't fix it, check the LLM model quality
# Some models are better at HTML than others
```

#### 2. Missing Semantic Structure
```python
# Check for semantic tags
semantic_tags = ['h1', 'h2', 'h3', 'p', 'ul', 'li', 'strong', 'em']
has_semantic = any(f"<{tag}" in response.content.lower() for tag in semantic_tags)

if not has_semantic:
    # LLM not using semantic HTML
    # Try more specific prompt
    response = await overlord.chat(
        "Create HTML with proper semantic tags like h1, h2, p, ul, and li"
    )
```

**Solution:**
1. HTML format automatically validates and fixes structure
2. BeautifulSoup handles most malformed HTML
3. For critical HTML, validate with your own parser
4. Request semantic tags explicitly in prompts

**Required Criteria:**
- Must have HTML tags (`<`, `>`)
- Must have semantic tags (`<h1>`, `<p>`, `<ul>`, `<li>`, etc.)
- Must not be JSON (negative validation)

---

## Plain Text Format Issues

### Issue: Text Has Formatting

**Symptoms:**
- Markdown syntax appears in "plain text"
- HTML tags present
- Inconsistent plain text output

**Diagnosis:**
```python
import re

overlord.response_format = "text"
response = await overlord.chat("Explain cloud computing")

# Check for unwanted formatting
markdown_patterns = [
    r"^#{1,6}\s+",      # Headers
    r"\*\*[^*]+\*\*",   # Bold
    r"`[^`]+`",         # Code
    r"```",             # Code blocks
]

has_markdown = any(re.search(p, response.content, re.MULTILINE) for p in markdown_patterns)
has_html = bool(re.search(r"<[^>]+>", response.content))

print(f"❌ Has markdown: {has_markdown}")
print(f"❌ Has HTML: {has_html}")
print(f"✅ Is plain text: {not has_markdown and not has_html}")
```

**Common Causes:**

#### 1. LLM Adding Formatting Despite Instructions
Some models default to markdown even when instructed not to.

```python
# Try emphasizing plain text in prompt
overlord.response_format = "text"
response = await overlord.chat(
    "Explain cloud computing in simple plain text "
    "without any markdown, HTML, or special formatting"
)
```

#### 2. Format Not Set
```python
# ❌ Wrong: Format not set, defaults to markdown
response = await overlord.chat("Explain")
# Result: Contains markdown formatting
```

```python
# ✅ Correct: Explicitly set text format
overlord.response_format = "text"
response = await overlord.chat("Explain")
# Result: Plain text
```

**Solution:**
1. Explicitly set format to "text"
2. Use prompts emphasizing plain, unformatted output
3. Consider post-processing to strip formatting if needed

**Post-Processing Cleanup:**
```python
import re

def strip_formatting(text):
    """Remove markdown and HTML from text."""
    # Remove markdown headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Remove bold/italic
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)

    # Remove code blocks
    text = re.sub(r"```[^`]*```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    return text.strip()

response = await overlord.chat("Explain")
clean_text = strip_formatting(response.content)
```

---

## Performance Issues

### Issue: Slow Response Times

**Expected Times (from e2e tests):**
- JSON: ~18-22 seconds
- Markdown: ~17-25 seconds
- HTML: ~23-36 seconds (validation overhead)
- Text: ~17-22 seconds

**If slower than expected:**

#### 1. Check Token Usage
```python
# Enable logging to see token counts
import logging
logging.basicConfig(level=logging.INFO)

overlord.response_format = "html"
response = await overlord.chat("Test")

# Look for token usage in logs
# High token counts = longer processing
```

#### 2. HTML Validation Overhead
HTML format adds ~5-10ms for BeautifulSoup validation:

```python
import time

# Compare formats
formats = ["text", "markdown", "html", "json"]
times = {}

for fmt in formats:
    overlord.response_format = fmt
    start = time.time()
    response = await overlord.chat("Quick test")
    times[fmt] = time.time() - start

# HTML should only be slightly slower
print(times)
# Expected: html ~5-10ms slower than text/markdown
```

**Solution:**
- Use text format for highest performance (no processing)
- Use JSON format for APIs (minimal processing)
- HTML validation overhead is unavoidable but minimal

---

## Testing Issues

### Issue: Format Tests Failing

**Symptoms:**
- Tests expect JSON but get markdown
- Validation assertions fail
- Inconsistent test results

**Diagnosis Script:**
```python
async def diagnose_format_issue():
    """Diagnose format configuration issues."""
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    # Check formation default
    print(f"Formation default: {overlord.response_format}")

    # Test each format
    for fmt in ["json", "markdown", "html", "text"]:
        overlord.response_format = fmt
        response = await overlord.chat("Test message")

        # Validate format
        is_valid = False
        if fmt == "json":
            try:
                data = json.loads(response.content)
                is_valid = "content" in data
            except:
                pass
        elif fmt == "markdown":
            is_valid = "#" in response.content or "```" in response.content
        elif fmt == "html":
            is_valid = "<" in response.content
        elif fmt == "text":
            is_valid = "<" not in response.content and "```" not in response.content

        status = "✅ PASS" if is_valid else "❌ FAIL"
        print(f"{fmt.upper()}: {status}")

        if not is_valid:
            print(f"  Content preview: {response.content[:100]}")

    await formation.stop_overlord()

# Run diagnosis
asyncio.run(diagnose_format_issue())
```

**Common Test Failures:**

#### 1. Format Not Reset Between Tests
```python
# ❌ Wrong: Format persists across tests
async def test_json():
    overlord.response_format = "json"
    # ... test ...

async def test_markdown():
    # Oops! Still JSON from previous test
    response = await overlord.chat("Test")
```

```python
# ✅ Correct: Reset format explicitly
async def test_markdown():
    overlord.response_format = "markdown"  # Explicit set
    response = await overlord.chat("Test")
```

#### 2. Validation Criteria Too Strict
```python
# ❌ Too strict: Markdown must have ALL elements
has_headers = "#" in content
has_code = "```" in content
has_lists = "-" in content or "*" in content
has_links = "[" in content and "](" in content
assert has_headers and has_code and has_lists and has_links
```

```python
# ✅ Appropriate: Markdown needs structure score ≥2
structure_score = sum([
    "#" in content,           # Headers
    "```" in content,         # Code blocks
    "-" in content,           # Lists
    "[" in content,           # Links
])
assert structure_score >= 2  # At least 2 elements
```

---

## Debug Strategies

### Enable Debug Logging

```python
import logging

# See format processing details
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

overlord.response_format = "html"
response = await overlord.chat("Test")
# Check logs for format processing steps
```

### Inspect Response Object

```python
response = await overlord.chat("Test")

print(f"Response type: {type(response)}")
print(f"Has content: {hasattr(response, 'content')}")
print(f"Content type: {type(response.content)}")
print(f"Content length: {len(response.content)}")
print(f"Content preview: {response.content[:200]}")
print(f"Format used: {overlord.response_format}")
```

### Test Format Pipeline

```python
async def test_format_pipeline():
    """Test complete format pipeline."""

    # 1. Load formation
    formation = Formation()
    await formation.load("formation.afs")
    print("✅ Formation loaded")

    # 2. Start overlord
    overlord = await formation.start_overlord()
    print(f"✅ Overlord started (default: {overlord.response_format})")

    # 3. Set format
    overlord.response_format = "json"
    print(f"✅ Format set: {overlord.response_format}")

    # 4. Send request
    response = await overlord.chat("Test message")
    print(f"✅ Response received (type: {type(response)})")

    # 5. Validate format
    try:
        data = json.loads(response.content)
        print(f"✅ JSON valid: {list(data.keys())}")
    except Exception as e:
        print(f"❌ JSON invalid: {e}")

    # 6. Cleanup
    await formation.stop_overlord()
    print("✅ Cleanup complete")

asyncio.run(test_format_pipeline())
```

---

## Getting Help

### Information to Provide

When reporting format issues, include:

1. **Formation configuration:**
   ```yaml
   overlord:
     response:
       format: "json"  # Your configuration
   ```

2. **Code snippet:**
   ```python
   overlord.response_format = "json"
   response = await overlord.chat("Test")
   ```

3. **Expected vs actual:**
   ```
   Expected: Valid JSON with content field
   Actual: Markdown text without JSON structure
   ```

4. **Response content sample:**
   ```
   First 200 characters of response.content
   ```

5. **Validation results:**
   ```python
   # Run diagnosis script and include output
   ```

### Next Steps

- **Documentation:** [Response Formats Guide](response-formats.md)
- **Configuration:** [Configuration Reference](../configuration/response-formats.md)
- **Quick Start:** [5-Minute Guide](response-formats-quickstart.md)
- **Tests:** Check `e2e/tests/11_formatting/` for working examples
