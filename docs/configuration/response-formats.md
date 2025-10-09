# Response Formats Configuration

This document explains how to configure response formats in MUXI Runtime formations, allowing you to customize how AI responses are formatted for different use cases and integrations.

## Overview

Response formats control how the Overlord presents AI-generated content to users. MUXI Runtime supports four formats:

- **Markdown** (default) - Rich text with headers, lists, and code blocks
- **Plain Text** - Clean, unformatted text for maximum compatibility
- **JSON** - Structured data for programmatic processing
- **HTML** - Semantic markup for web integration

## Basic Configuration

### Formation YAML Configuration

Configure response formats in your `formation.yaml`:

```yaml
schema: "1.0.0"
id: "my-assistant"
description: "Assistant with custom response formatting"

overlord:
  persona: "You are a helpful assistant"

  # Response configuration
  response:
    format: "markdown"           # Primary format setting
    streaming: false             # Enable streaming responses
    interactive_elements: true   # Reserved for future widgets feature

agents:
  - id: assistant
    name: "Assistant"
    # ... agent configuration
```

### Configuration Options

#### `overlord.response.format`
- **Type**: `string`
- **Default**: `"markdown"`
- **Options**: `"markdown"`, `"text"`, `"json"`, `"html"`
- **Description**: Sets the default response format for all AI responses

#### `overlord.response.streaming`
- **Type**: `boolean`
- **Default**: `false`
- **Description**: Enable streaming responses (works with all formats)

#### `overlord.response.interactive_elements`
- **Type**: `boolean`
- **Default**: `true`
- **Description**: Reserved for future widgets feature

## Format-Specific Examples

### Markdown Format (Default)

Best for documentation, rich text responses, and general usage:

```yaml
overlord:
  response:
    format: "markdown"
```

**Output Example:**
```markdown
# Benefits of Cloud Computing

Cloud computing offers several key advantages:

## Cost Efficiency
- **Reduced costs** through pay-as-you-use pricing
- **Lower maintenance** with managed infrastructure

## Code Example
```python
# Deploy to cloud
app.deploy(region="us-east-1")
```
```

### Plain Text Format

Best for CLI applications, logs, and simple integrations:

```yaml
overlord:
  response:
    format: "text"
```

**Output Example:**
```
Cloud Computing Benefits

1. Cost Efficiency
   Reduces infrastructure costs through pay-as-you-use pricing
   and eliminates physical server maintenance needs.

2. Scalability
   Provides elastic resources that automatically grow with
   your needs during peak usage times.
```

### JSON Format

Best for APIs, structured data exchange, and programmatic processing:

```yaml
overlord:
  response:
    format: "json"
```

**Output Example:**
```json
{
  "content": "Cloud computing offers cost efficiency through pay-as-you-use pricing, scalability with elastic resources, and global accessibility for remote access to applications.",
  "type": "response",
  "format": "json"
}
```

### HTML Format

Best for web applications, email templates, and rich UI integration:

```yaml
overlord:
  response:
    format: "html"
```

**Output Example:**
```html
<h1>Cloud Computing Benefits</h1>
<ul>
    <li><strong>Cost Efficiency:</strong> Pay-as-you-use pricing</li>
    <li><strong>Scalability:</strong> Elastic resources</li>
    <li><strong>Global Access:</strong> Remote accessibility</li>
</ul>
```

## Advanced Configuration

### Environment-Specific Formats

Configure different formats for different environments:

```yaml
# Development formation - markdown for readability
overlord:
  response:
    format: "markdown"
    streaming: true    # Enable for debugging
```

```yaml
# Production API formation - JSON for integration
overlord:
  response:
    format: "json"
    streaming: false   # Batch responses for reliability
```

### Combined Configuration with Other Features

Response formats work with all other MUXI Runtime features:

```yaml
overlord:
  persona: "You are a technical documentation assistant"

  response:
    format: "html"               # Rich HTML output
    streaming: true              # Real-time generation
    interactive_elements: true   # Future widgets support

  clarification:
    style: conversational
    max_rounds:
      direct: 3

  # Workflow integration
  auto_decomposition: true
  complexity_threshold: 7.0

agents:
  - id: docs_writer
    specialization: "technical documentation"
    # ... agent config

memory:
  buffer_size: 100
  # ... memory config
```

## Runtime Override

You can override the formation's default format at runtime:

```python
from muxi.runtime import Formation

# Load formation with default format
formation = Formation()
await formation.load("formation.yaml")
overlord = await formation.start_overlord()

# Override format for specific interactions
overlord.response_format = "json"
response = await overlord.chat("List the benefits of cloud computing")
print(response.content)  # JSON format

# Reset to formation default
overlord.response_format = None
response = await overlord.chat("Explain containers")
print(response.content)  # Back to formation default (e.g., markdown)
```

## Integration Patterns

### Web Application Integration

```yaml
# Web app formation - HTML format for direct embedding
overlord:
  response:
    format: "html"
    streaming: true

agents:
  - id: content_generator
    specialization: "web content"
```

```python
# Web controller usage
overlord.response_format = "html"
response = await overlord.chat("Create a product overview")

# Embed directly in template
return render_template('page.html', content=response.content)
```

### API Server Integration

```yaml
# API server formation - JSON for structured responses
overlord:
  response:
    format: "json"
    streaming: false  # Consistent API responses
```

```python
# API endpoint usage
@app.post("/api/chat")
async def chat_api(message: str):
    overlord.response_format = "json"
    response = await overlord.chat(message)
    return JSONResponse(content=response.content)
```

### CLI Tool Integration

```yaml
# CLI tool formation - text format for terminal output
overlord:
  response:
    format: "text"
```

```python
# CLI command usage
@click.command()
def ask(question: str):
    overlord.response_format = "text"
    response = await overlord.chat(question)
    click.echo(response.content)  # Clean terminal output
```

## Validation and Error Handling

### Configuration Validation

MUXI Runtime validates response format configurations:

```yaml
overlord:
  response:
    format: "invalid_format"  # ❌ Will cause formation load error
```

**Error Message:**
```
ValidationError: overlord.response.format must be one of: "json", "text", "markdown", "html"
```

### Runtime Validation

Runtime format overrides are also validated:

```python
try:
    overlord.response_format = "xml"  # ❌ Unsupported format
except ValueError as e:
    print(f"Invalid format: {e}")
```

### Graceful Fallback

If format processing fails, MUXI Runtime falls back to the formation default:

```python
# HTML processing fails -> falls back to formation default
overlord.response_format = "html"
response = await overlord.chat("Complex formatting request")
# If HTML processing fails, uses formation's default format
```

## Performance Considerations

### Format Processing Overhead

| Format | Processing Time | Memory Usage | Streaming Support |
|--------|----------------|--------------|------------------|
| Text | Fastest (0ms) | Lowest | ✅ Native |
| Markdown | Fast (0ms) | Low | ✅ Native |
| HTML | Moderate (+5-10ms) | Medium | ✅ Validated |
| JSON | Fast (+1-2ms) | Low | ✅ Wrapped |

### Recommendations

**For High-Performance APIs:**
```yaml
overlord:
  response:
    format: "json"      # Minimal processing overhead
    streaming: false    # Batch for consistency
```

**For Rich User Interfaces:**
```yaml
overlord:
  response:
    format: "html"      # Rich formatting with validation
    streaming: true     # Real-time user experience
```

**For CLI and Logging:**
```yaml
overlord:
  response:
    format: "text"      # No processing overhead
    streaming: false    # Clean batch output
```

## Migration Guide

### From Text-Only Formations

**Before** (text-only responses):
```yaml
overlord:
  persona: "You are an assistant"
  # No response format configuration
```

**After** (explicit format configuration):
```yaml
overlord:
  persona: "You are an assistant"
  response:
    format: "markdown"  # Explicit format choice
```

### From Custom Formatting Solutions

**Before** (manual formatting):
```python
response = await overlord.chat("Generate report")
html_content = custom_markdown_to_html(response.content)
```

**After** (native HTML support):
```yaml
overlord:
  response:
    format: "html"  # Native HTML generation
```

```python
response = await overlord.chat("Generate report")
html_content = response.content  # Already HTML
```

## Troubleshooting

### Common Issues

**Q: Format not applying to responses**
```yaml
# ❌ Wrong: format not under response
overlord:
  format: "json"

# ✅ Correct: format under response section
overlord:
  response:
    format: "json"
```

**Q: HTML tags are malformed**
- HTML format uses BeautifulSoup for automatic validation and fixing
- Check that the LLM model supports HTML generation
- Consider using markdown format if consistent structure is critical

**Q: JSON responses aren't valid**
- JSON format automatically wraps content in valid structure
- Content is guaranteed to be valid JSON
- Check that you're accessing `response.content` correctly

**Q: Streaming not working with format**
- All formats support streaming
- Check that `streaming: true` is set in configuration
- Verify your client can handle streaming responses

### Debug Configuration

Enable debug logging to troubleshoot format processing:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Format processing details will be logged
overlord.response_format = "html"
response = await overlord.chat("Test message")
```

### Validation Commands

Validate your formation configuration:

```bash
# Using MUXI CLI (if available)
muxi validate formation.yaml

# Or check with Python
python -c "
from muxi.runtime import Formation
formation = Formation()
formation.load('formation.yaml')
print('✅ Configuration valid')
"
```

### Testing Format Configuration

Test your configured format is working correctly:

```python
import asyncio
import json
import re
from muxi.runtime import Formation

async def test_format_configuration():
    """Test that formation's configured format works correctly."""
    # Load formation
    formation = Formation()
    await formation.load("formation.yaml")
    overlord = await formation.start_overlord()

    # Test with the formation's default format
    response = await overlord.chat("List three benefits of cloud computing")

    # Validate based on configured format
    config_format = overlord.response_format or "markdown"  # Default

    if config_format == "json":
        # JSON validation
        parsed = json.loads(response.content)
        assert "content" in parsed and "type" in parsed
        assert parsed["format"] == "json"
        print(f"✅ JSON format configured correctly")

    elif config_format == "markdown":
        # Markdown validation
        has_structure = bool(re.search(r"^#{1,6}\s+", response.content, re.MULTILINE))
        has_code = "```" in response.content or "`" in response.content
        structure_score = sum([has_structure, has_code])

        # Negative validation: should not be JSON
        try:
            json.loads(response.content)
            print("❌ Markdown format producing JSON")
        except json.JSONDecodeError:
            print(f"✅ Markdown format configured correctly (score: {structure_score}/2)")

    elif config_format == "html":
        # HTML validation
        has_tags = bool(re.search(r"<[^>]+>", response.content))
        semantic_tags = ["h1", "h2", "h3", "p", "ul", "li"]
        has_semantic = any(f"<{tag}" in response.content.lower() for tag in semantic_tags)

        assert has_tags and has_semantic
        print(f"✅ HTML format configured correctly")

    elif config_format == "text":
        # Plain text validation
        has_markdown = bool(re.search(r"^#{1,6}\s+|\*\*[^*]+\*\*", response.content, re.MULTILINE))
        has_html = bool(re.search(r"<[^>]+>", response.content))

        assert not has_markdown and not has_html
        print(f"✅ Plain text format configured correctly")

    await formation.stop_overlord()

# Run test
asyncio.run(test_format_configuration())
```

## Best Practices

### Format Selection Guidelines

1. **Choose markdown** for general-purpose usage and documentation
2. **Choose text** for CLI tools and log generation
3. **Choose JSON** for APIs and structured data exchange
4. **Choose HTML** for web applications and rich UI integration

### Configuration Management

```yaml
# ✅ Good: Explicit configuration with comments
overlord:
  response:
    format: "markdown"    # Default for documentation
    streaming: false      # Batch responses for stability

# ❌ Avoid: Implicit defaults without documentation
overlord:
  # No response configuration - unclear intent
```

### Environment Configuration

Use different formations for different environments:

- `formation-dev.yaml` - markdown format for readability
- `formation-prod.yaml` - json format for API consistency
- `formation-cli.yaml` - text format for terminal usage

### Testing Format Configurations

Test all configured formats:

```python
# Test configuration for each format
formats = ["json", "text", "markdown", "html"]

for format_name in formats:
    overlord.response_format = format_name
    response = await overlord.chat("Test message")

    print(f"✅ {format_name} format working")
    assert response.content, f"Empty response for {format_name}"
```

## Conclusion

Response formats provide flexible output options while maintaining the simplicity of MUXI Runtime's formation-based configuration. Choose the format that best matches your integration needs, and leverage the runtime override capability for dynamic format selection.

The LLM-based approach ensures natural, contextually appropriate formatting while post-processing guarantees technical correctness for structured formats like JSON and HTML.