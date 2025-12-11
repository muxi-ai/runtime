# Response Formats - Quick Start Guide

A practical guide to using MUXI Runtime's response format features.

## 5-Minute Quick Start

### 1. Configure Your Formation

Edit your `formation.afs`:

```yaml
overlord:
  response:
    format: "markdown"  # Choose: "json", "markdown", "html", or "text"
```

### 2. Use Runtime Override

```python
from muxi.runtime import Formation

formation = Formation()
await formation.load("formation.afs")
overlord = await formation.start_overlord()

# Change format at runtime
overlord.response_format = "json"
response = await overlord.chat("List benefits of cloud computing")
```

### 3. Validate the Output

```python
import json

# For JSON format
if overlord.response_format == "json":
    data = json.loads(response.content)
    print(data["content"])

# For other formats
else:
    print(response.content)
```

## Common Use Cases

### API Server (JSON Format)

**Formation:**
```yaml
overlord:
  response:
    format: "json"
```

**Code:**
```python
@app.post("/api/chat")
async def chat(message: str):
    overlord.response_format = "json"
    response = await overlord.chat(message)
    return JSONResponse(content=response.content)
```

**Output:**
```json
{
  "content": "Cloud computing offers cost efficiency, scalability, and global accessibility.",
  "type": "response",
  "format": "json"
}
```

### Web Application (HTML Format)

**Formation:**
```yaml
overlord:
  response:
    format: "html"
```

**Code:**
```python
overlord.response_format = "html"
response = await overlord.chat("Create a benefits overview")
# Embed directly in your template
```

**Output:**
```html
<h1>Cloud Computing Benefits</h1>
<ul>
    <li><strong>Cost Efficiency:</strong> Pay-as-you-use pricing</li>
    <li><strong>Scalability:</strong> Elastic resources</li>
</ul>
```

### CLI Tool (Plain Text Format)

**Formation:**
```yaml
overlord:
  response:
    format: "text"
```

**Code:**
```python
overlord.response_format = "text"
response = await overlord.chat(question)
print(response.content)  # Clean terminal output
```

**Output:**
```
Cloud Computing Benefits

1. Cost Efficiency - Reduces infrastructure costs through
   pay-as-you-use pricing models.

2. Scalability - Provides elastic resources that grow with
   your needs automatically.
```

### Documentation Generator (Markdown Format)

**Formation:**
```yaml
overlord:
  response:
    format: "markdown"
```

**Code:**
```python
overlord.response_format = "markdown"
response = await overlord.chat("Create API documentation for user endpoint")
# Save directly to .md file
```

**Output:**
```markdown
# User API Documentation

## Endpoint: `/api/users`

### GET Request
```python
response = requests.get('/api/users')
```

### Response
Returns a list of user objects with the following fields:
- `id` - Unique user identifier
- `email` - User email address
```

## Format Comparison

| Format | Use Case | Validation | Processing Time |
|--------|----------|------------|-----------------|
| **JSON** | APIs, structured data | Automatic wrapping | ~1-2ms overhead |
| **Markdown** | Documentation, rich text | LLM-based | No overhead |
| **HTML** | Web apps, email | BeautifulSoup | ~5-10ms overhead |
| **Text** | CLI, logs, simple output | LLM-based | No overhead |

## Testing Your Format

### Quick Validation Script

```python
import asyncio
import json
import re
from muxi.runtime import Formation

async def test_format():
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    # Test JSON
    overlord.response_format = "json"
    response = await overlord.chat("Test message")
    data = json.loads(response.content)
    assert "content" in data
    print("✅ JSON format works")

    # Test Markdown
    overlord.response_format = "markdown"
    response = await overlord.chat("Create a code example")
    assert "#" in response.content or "```" in response.content
    print("✅ Markdown format works")

    # Test HTML
    overlord.response_format = "html"
    response = await overlord.chat("Create a list")
    assert "<" in response.content and ">" in response.content
    print("✅ HTML format works")

    # Test Plain Text
    overlord.response_format = "text"
    response = await overlord.chat("Simple explanation")
    assert "<" not in response.content  # No HTML
    assert "```" not in response.content  # No markdown
    print("✅ Plain text format works")

    await formation.stop_overlord()

asyncio.run(test_format())
```

## Common Pitfalls

### ❌ Wrong: Format Outside Response Block
```yaml
overlord:
  format: "json"  # Wrong location
```

### ✅ Correct: Format Inside Response Block
```yaml
overlord:
  response:
    format: "json"  # Correct location
```

### ❌ Wrong: Invalid Format Name
```python
overlord.response_format = "xml"  # Not supported
```

### ✅ Correct: Valid Format Name
```python
overlord.response_format = "json"  # Supported
```

### ❌ Wrong: Not Checking Format Before Parsing
```python
data = json.loads(response.content)  # May fail if not JSON format
```

### ✅ Correct: Check Format First
```python
if overlord.response_format == "json":
    data = json.loads(response.content)
else:
    content = response.content
```

## Troubleshooting

### Problem: "Format not applying"
**Check:**
1. Format set before calling `overlord.chat()`?
2. Correct format name (json/markdown/html/text)?
3. Format in correct YAML location (`overlord.response.format`)?

### Problem: "Invalid JSON response"
**Solution:** JSON format automatically wraps content. Check you're accessing `response.content`, not `response`.

### Problem: "Markdown has no structure"
**Solution:** Markdown relies on LLM instructions. Try more specific prompts like "Create documentation with headers and code examples".

### Problem: "HTML tags malformed"
**Solution:** HTML format uses BeautifulSoup for validation. The system automatically fixes most issues.

## Next Steps

- **Full Documentation:** [Response Formats](response-formats.md)
- **Configuration Reference:** [Configuration Guide](../configuration/response-formats.md)
- **Testing Guide:** See e2e tests in `e2e/tests/11_formatting/`

## Performance Tips

1. **JSON format**: Fastest for APIs (~1-2ms processing overhead)
2. **Plain text format**: Fastest for CLI (no processing overhead)
3. **Markdown format**: Good balance of readability and speed
4. **HTML format**: Slightly slower due to validation (~5-10ms overhead)

## FAQ

**Q: Can I mix formats in one formation?**
A: Yes! Use runtime override: `overlord.response_format = "json"`

**Q: Does streaming work with all formats?**
A: Yes, all formats support streaming.

**Q: Which format is default?**
A: Markdown is the default if not specified.

**Q: Can I add custom formats?**
A: Not currently. Use the four supported formats: json, markdown, html, text.

**Q: How do I test format configurations?**
A: See the validation script above or check e2e tests in `e2e/tests/11_formatting/`.
