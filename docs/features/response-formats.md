# Response Formats

MUXI Runtime supports multiple response formats to accommodate different use cases and integration requirements. Users can receive responses in JSON, Markdown, Plain Text, or HTML formats based on their configuration.

## Overview

The response format system uses **LLM persona instructions** to generate naturally formatted content, combined with **post-processing validation** for structured formats. This hybrid approach ensures high-quality, contextually appropriate responses while maintaining technical correctness.

### Supported Formats

| Format | Best For | Output Type | Validation |
|--------|----------|-------------|------------|
| **Markdown** | Documentation, Rich text, Default usage | `.md` with headers, lists, code blocks | LLM-based |
| **Plain Text** | Simple integrations, CLI output, Logs | Clean text, no formatting | LLM-based |
| **JSON** | APIs, Structured data, Programmatic access | Wrapped JSON structure | Post-processed |
| **HTML** | Web integration, Rich UI, Email templates | Semantic HTML tags | BeautifulSoup validation |

## Configuration

### Formation YAML

Configure the default response format in your formation:

```yaml
# formation.afs (or .yaml)
schema: "1.0.0"
id: "my-assistant"

overlord:
  persona: "You are a helpful assistant"

  # Response configuration
  response:
    format: "markdown"           # Default format: "json", "text", "markdown", "html"
    streaming: false             # Works with all formats
    interactive_elements: true   # Reserved for future widgets feature

agents:
  - id: assistant
    # ... agent configuration
```

### Runtime Override

You can also set the format dynamically at runtime:

```python
# Set format for specific interactions
overlord.response_format = "json"
response = await overlord.chat("List the benefits of cloud computing")

# Reset to formation default
overlord.response_format = None
```

## Format Details

### 1. Markdown Format (Default)

**Use Cases:**
- Documentation generation
- Rich text responses with structure
- Content that needs formatting without HTML complexity

**Features:**
- Headers (`#`, `##`, `###`)
- **Bold** and *italic* text
- Code blocks with syntax highlighting
- Lists (bulleted and numbered)
- Links and references

**Example:**
```python
overlord.response_format = "markdown"
response = await overlord.chat("Explain the benefits of cloud computing")
print(response.content)
```

**Output:**
```markdown
# Benefits of Cloud Computing

Cloud computing offers several key advantages:

## Cost Efficiency
- **Reduced infrastructure costs** - No need for physical servers
- **Pay-as-you-use** pricing models
- Lower maintenance expenses

## Scalability
- **Elastic resources** that grow with your needs
- Automatic scaling during peak times
- Global reach with multiple data centers

## Code Example
```python
# Deploy to cloud
app.deploy(region="us-east-1", scale="auto")
```
```

### 2. Plain Text Format

**Use Cases:**
- CLI applications
- Log file generation
- Simple API responses
- Integration with text-only systems

**Features:**
- Clean, unformatted text
- Line breaks for structure
- No special characters or markup
- Maximum compatibility

**Example:**
```python
overlord.response_format = "text"
response = await overlord.chat("List three benefits of cloud computing")
print(response.content)
```

**Output:**
```
Cloud computing offers three key benefits:

1. Cost Efficiency
   Reduces infrastructure costs through pay-as-you-use pricing and eliminates
   the need for physical server maintenance.

2. Scalability
   Provides elastic resources that automatically grow with your needs and
   scale during peak usage times.

3. Global Accessibility
   Enables access to applications and data from anywhere with internet
   connectivity across multiple regions.
```

### 3. JSON Format

**Use Cases:**
- REST API responses
- Structured data exchange
- Programmatic processing
- Integration with JSON-based systems

**Features:**
- Valid JSON structure
- Consistent envelope format
- Content wrapped with metadata
- Machine-readable format

**Example:**
```python
overlord.response_format = "json"
response = await overlord.chat("What are the main benefits of cloud computing?")
print(response.content)
```

**Output:**
```json
{
  "content": "Cloud computing offers several key benefits including cost efficiency through pay-as-you-use pricing, scalability with elastic resources that grow with your needs, and global accessibility allowing access to applications from anywhere with internet connectivity.",
  "type": "response",
  "format": "json"
}
```

### 4. HTML Format

**Use Cases:**
- Web applications
- Email templates
- Rich UI integration
- Content management systems

**Features:**
- Semantic HTML tags (`<h1>`, `<p>`, `<ul>`, `<li>`)
- Proper tag structure and nesting
- BeautifulSoup validation and formatting
- Web-ready markup

**Example:**
```python
overlord.response_format = "html"
response = await overlord.chat("Create a simple guide on cloud computing benefits")
print(response.content)
```

**Output:**
```html
<h1>Cloud Computing Benefits</h1>

<p>Cloud computing provides numerous advantages for modern businesses:</p>

<h2>Key Benefits</h2>

<ul>
    <li>
        <strong>Cost Efficiency:</strong>
        Pay-as-you-use pricing eliminates upfront infrastructure costs
    </li>
    <li>
        <strong>Scalability:</strong>
        Resources automatically scale with demand
    </li>
    <li>
        <strong>Global Access:</strong>
        Access applications from anywhere with internet connectivity
    </li>
</ul>

<h2>Implementation</h2>

<p>Getting started with cloud computing involves:</p>
<ol>
    <li>Assess your current infrastructure needs</li>
    <li>Choose a cloud provider</li>
    <li>Migrate applications gradually</li>
</ol>
```

## Technical Implementation

### LLM Persona Instructions

The system enhances the overlord's persona with format-specific instructions:

```python
# Internal implementation (for reference)
if self.response_format == "markdown":
    format_instruction = """
    Format your response using proper markdown with headers (# ## ###),
    bullet points, bold/italic text, and code blocks where appropriate.
    """
elif self.response_format == "text":
    format_instruction = """
    Format your response as plain text with no markdown formatting,
    special characters, or HTML. Use simple text formatting like
    line breaks and spacing.
    """
elif self.response_format == "html":
    format_instruction = """
    Format your response as valid HTML with proper semantic tags like
    <h1>, <h2>, <p>, <ul>, <li>, <strong>, <em>, and <code>. Include
    proper structure and ensure all tags are properly closed.
    """
```

### Post-Processing Pipeline

Different formats receive different post-processing:

1. **JSON**: Content wrapped in structured envelope
2. **HTML**: BeautifulSoup validation and formatting
3. **Markdown/Text**: Direct LLM output (no post-processing)

### Streaming Compatibility

All formats work seamlessly with streaming responses:

- **Markdown/Text**: Stream naturally as generated
- **HTML**: Stream as text, validate on completion
- **JSON**: Stream content, wrap in JSON structure on completion

## Best Practices

### Format Selection Guidelines

**Choose Markdown when:**
- Users need readable, formatted text
- Content includes code examples or technical documentation
- You want rich formatting without HTML complexity

**Choose Plain Text when:**
- Integrating with legacy systems
- Generating log files or CLI output
- Maximum compatibility is required
- Processing content programmatically without markup

**Choose JSON when:**
- Building REST APIs or webhooks
- Need structured, machine-readable responses
- Integrating with JSON-based systems
- Require consistent envelope format

**Choose HTML when:**
- Embedding in web applications
- Creating email templates
- Need semantic markup for accessibility
- Integrating with content management systems

### Configuration Tips

1. **Set formation default** for consistent behavior
2. **Use runtime override** for specific interactions
3. **Test with streaming** if using real-time features
4. **Validate HTML output** in your application if using HTML format

### Error Handling

All formats include proper error handling:

```python
try:
    overlord.response_format = "html"
    response = await overlord.chat("Generate a report")

    # HTML validation happens automatically
    if response.content:
        # HTML is validated and formatted
        print("Valid HTML received")

except Exception as e:
    # Falls back gracefully to formation default
    print(f"Error: {e}")
```

## Integration Examples

### Web Application Integration

```python
from muxi.runtime import Formation

# Load formation with HTML format for web
formation = Formation()
await formation.load("formation.yaml")
overlord = await formation.start_overlord()

# Generate web-ready content
overlord.response_format = "html"
response = await overlord.chat("Create a product overview page")

# Directly embed in web template
html_content = response.content  # Already validated HTML
```

### API Server Integration

```python
from fastapi import FastAPI
from muxi.runtime import Formation

app = FastAPI()

@app.post("/chat")
async def chat_endpoint(message: str):
    # Force JSON format for API responses
    overlord.response_format = "json"
    response = await overlord.chat(message)

    # Response is already valid JSON
    return JSONResponse(content=response.content)
```

### CLI Tool Integration

```python
import click
from muxi.runtime import Formation

@click.command()
@click.option('--format', default='text', help='Output format')
def ask(question: str, format: str):
    overlord.response_format = format
    response = await overlord.chat(question)

    # Clean output for terminal
    click.echo(response.content)
```

## Advanced Features

### Dynamic Format Detection

You can implement smart format detection based on user context:

```python
def detect_preferred_format(user_agent: str, accept_header: str) -> str:
    if 'application/json' in accept_header:
        return 'json'
    elif 'text/html' in accept_header:
        return 'html'
    elif 'text/plain' in accept_header:
        return 'text'
    else:
        return 'markdown'  # Default

# Use in request handling
preferred_format = detect_preferred_format(request.headers.get('user-agent'))
overlord.response_format = preferred_format
```

### Format Validation

For critical applications, validate format before processing:

```python
SUPPORTED_FORMATS = {'json', 'markdown', 'text', 'html'}

def set_safe_format(format_name: str) -> str:
    if format_name not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {format_name}")
    return format_name

# Safe format setting
overlord.response_format = set_safe_format(user_requested_format)
```

## Validation and Testing

### Format Validation

Each format has specific validation criteria:

#### JSON Format Validation
```python
import json

# Validate JSON format
overlord.response_format = "json"
response = await overlord.chat("List three benefits of cloud computing")

# Test 1: Valid JSON parsing
try:
    parsed = json.loads(response.content)
    print("✅ Valid JSON structure")
except json.JSONDecodeError:
    print("❌ Invalid JSON")

# Test 2: Required fields present
required_fields = ["content", "type", "format"]
if all(field in parsed for field in required_fields):
    print("✅ All required fields present")

# Test 3: Correct field values
assert parsed["type"] == "response"
assert parsed["format"] == "json"
print("✅ Field values correct")
```

#### Markdown Format Validation
```python
import re

# Validate markdown format
overlord.response_format = "markdown"
response = await overlord.chat("Create documentation for a Python project")

# Test 1: Has headers
has_headers = bool(re.search(r"^#{1,6}\s+", response.content, re.MULTILINE))
print(f"✅ Has headers: {has_headers}")

# Test 2: Has code blocks
has_code = "```" in response.content or "`" in response.content
print(f"✅ Has code blocks: {has_code}")

# Test 3: Not JSON (negative validation)
try:
    json.loads(response.content)
    print("❌ Should not be JSON")
except json.JSONDecodeError:
    print("✅ Correctly formatted as Markdown")
```

#### HTML Format Validation
```python
from bs4 import BeautifulSoup
import re

# Validate HTML format
overlord.response_format = "html"
response = await overlord.chat("Create a webpage about cloud benefits")

# Test 1: Has HTML tags
has_html_tags = bool(re.search(r"<[^>]+>", response.content))
print(f"✅ Has HTML tags: {has_html_tags}")

# Test 2: Has semantic tags
semantic_tags = ["h1", "h2", "h3", "p", "ul", "li", "strong"]
has_semantic = any(f"<{tag}" in response.content.lower() for tag in semantic_tags)
print(f"✅ Has semantic tags: {has_semantic}")

# Test 3: Valid HTML structure
try:
    soup = BeautifulSoup(response.content, 'html.parser')
    print(f"✅ Valid HTML structure with {len(soup.find_all())} tags")
except Exception as e:
    print(f"❌ Invalid HTML: {e}")
```

#### Plain Text Format Validation
```python
import re

# Validate plain text format
overlord.response_format = "text"
response = await overlord.chat("Explain machine learning in simple terms")

# Test 1: No markdown formatting
markdown_patterns = [r"^#{1,6}\s+", r"\*\*[^*]+\*\*", r"```", r"`[^`]+`"]
has_markdown = any(re.search(p, response.content, re.MULTILINE) for p in markdown_patterns)
print(f"✅ No markdown: {not has_markdown}")

# Test 2: No HTML tags
has_html = bool(re.search(r"<[^>]+>", response.content))
print(f"✅ No HTML: {not has_html}")

# Test 3: Is plain text
is_plain_text = not has_markdown and not has_html
print(f"✅ Is plain text: {is_plain_text}")
```

### Testing All Formats

Automated test for format consistency:

```python
async def test_all_formats():
    """Test all response formats are working correctly."""
    formats = ["json", "markdown", "html", "text"]
    results = {}

    for fmt in formats:
        overlord.response_format = fmt
        response = await overlord.chat("List three benefits of cloud computing")

        # Basic validation
        if fmt == "json":
            try:
                parsed = json.loads(response.content)
                results[fmt] = "content" in parsed and "type" in parsed
            except:
                results[fmt] = False

        elif fmt == "markdown":
            has_structure = "#" in response.content or "```" in response.content
            not_json = True
            try:
                json.loads(response.content)
                not_json = False
            except:
                pass
            results[fmt] = has_structure and not_json

        elif fmt == "html":
            has_tags = "<" in response.content and ">" in response.content
            results[fmt] = has_tags

        elif fmt == "text":
            # Should be plain text without formatting
            results[fmt] = "<" not in response.content and "```" not in response.content

    # Print results
    for fmt, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{fmt.upper()}: {status}")

    return all(results.values())
```

## Troubleshooting

### Common Issues

**Q: HTML tags are malformed**
A: BeautifulSoup automatically validates and fixes HTML structure. If issues persist, check the LLM model's HTML generation capabilities. The system uses semantic tags like `<h1>`, `<h2>`, `<p>`, `<ul>`, `<li>` for proper structure.

**Q: JSON responses aren't valid**
A: JSON format uses post-processing to ensure validity. The content is automatically wrapped in a valid JSON structure with required fields: `content`, `type`, and `format`. If you're seeing invalid JSON, check that you're accessing `response.content` correctly.

**Q: Markdown formatting inconsistent**
A: Markdown relies on LLM instructions. The system expects structure score ≥2 (headers, code blocks, lists, links, emphasis). Consider using more specific prompts or switching to HTML for guaranteed structure.

**Q: Format not applying to responses**
A: Check that `overlord.response_format` is set before calling `overlord.chat()`. Runtime setting overrides formation configuration. Also verify the format name is one of: "json", "markdown", "html", "text".

**Q: Format validation failing in tests**
A: Different formats have different validation criteria:
- **JSON**: Must parse successfully and have required fields
- **Markdown**: Must have structure score ≥2 (presence of headers, code blocks, etc.)
- **HTML**: Must have HTML tags and semantic tags
- **Text**: Must be plain text without markdown or HTML

### Debug Mode

Enable debug logging to see format processing:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

overlord.response_format = "html"
response = await overlord.chat("Test message")
# Check logs for format processing details
```

### Performance Metrics

Expected performance characteristics from e2e tests:

- **JSON Test**: ~18-22 seconds average
- **Markdown Test**: ~17-25 seconds average
- **HTML Test**: ~23-36 seconds average (includes validation)
- **Text Test**: ~17-22 seconds average
- **Overall Average**: ~24 seconds per format test

Token usage per test:
- Embedding tokens: ~100-300
- LLM tokens: ~5,000-6,500 (input + output)
- Total for full suite: ~25,000-30,000 tokens

## Related Documentation

- **[Quick Start Guide](response-formats-quickstart.md)** - 5-minute guide to get started
- **[Configuration Reference](../configuration/response-formats.md)** - Detailed configuration options
- **[Troubleshooting Guide](response-formats-troubleshooting.md)** - Common issues and solutions

## Migration Guide

### From Text-Only Systems

```python
# Before: Text-only responses
response = await overlord.chat("Generate report")
text_content = response.content

# After: Multi-format support
overlord.response_format = "markdown"  # or "html", "json"
response = await overlord.chat("Generate report")
formatted_content = response.content
```

### From Custom Formatting

```python
# Before: Manual formatting
response = await overlord.chat("Generate report")
html_content = markdown_to_html(response.content)

# After: Native HTML support
overlord.response_format = "html"
response = await overlord.chat("Generate report")
html_content = response.content  # Already valid HTML
```

## Performance Considerations

- **Markdown/Text**: Fastest (no post-processing)
- **HTML**: Slight overhead for BeautifulSoup validation (~5-10ms)
- **JSON**: Minimal overhead for structure wrapping (~1-2ms)
- **Streaming**: All formats maintain streaming performance

## Conclusion

Response formats in MUXI Runtime provide flexible output options without sacrificing quality or performance. The LLM-based approach ensures natural, contextually appropriate formatting while post-processing guarantees technical correctness for structured formats.

Choose the format that best fits your use case, and leverage the hybrid approach to get both natural language quality and technical reliability in your AI applications.