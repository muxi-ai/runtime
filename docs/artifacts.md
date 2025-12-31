# Artifacts System

The MUXI Runtime artifacts system provides intelligent file generation, tracking, and management capabilities for AI agents. It enables agents to create, store, and retrieve files while maintaining complete traceability and secure execution.

## Overview

The artifacts system consists of several key components:

- **Artifact Service**: Core service for secure sandboxed execution and file generation
- **Artifact Processor**: Conversion of raw files into standardized artifact objects with base64 encoding
- **Artifact Extractor**: Intelligent parsing of tool results into structured artifacts
- **Agent Integration**: Seamless integration with agents via the `generate_file` tool

## Key Features

### 🔒 **Secure File Generation**
- Sandboxed Python execution with whitelisted imports
- Memory and execution time limits
- AST-based code validation
- No network access or dangerous operations

### 📁 **Intelligent File Processing**
- Automatic MIME type detection
- Base64 data URL generation
- Metadata extraction (size, timestamps)
- Format classification (text, chart, document, etc.)

### 🗃️ **Session-Based Storage**
- Artifacts organized by session ID
- Automatic cleanup of old artifacts
- Nanoid-based unique identifiers with 3-letter prefixes
- Fast retrieval by session and time filters

### 🔍 **Comprehensive Tracking**
- Full audit trail of file generation
- Tool execution results preserved
- Artifact metadata and provenance
- Integration with agent responses

## Architecture

```
┌───────────────────────────────────────────┐
│               User Request                │
│        "Create a PDF report..."           │
└─────────────────────┬─────────────────────┘
                      │
┌─────────────────────▼─────────────────────┐
│                   Agent                   │
│         Calls generate_file tool          │
└─────────────────────┬─────────────────────┘
                      │
┌─────────────────────▼─────────────────────┐
│              Artifact Service             │
│  ┌──────────────────────────────────────┐ │
│  │  1. Code Validation (AST)            │ │
│  │  2. Sandboxed Execution              │ │
│  │  3. File Tracking                    │ │
│  │  4. Create Artifact Object           │ │
│  └──────────────────────────────────────┘ │
└─────────────────────┬─────────────────────┘
                      │
┌─────────────────────▼─────────────────────┐
│            Artifact Processor             │
│  ┌──────────────────────────────────────┐ │
│  │  1. Read Generated File              │ │
│  │  2. Create Base64 Data URL           │ │
│  │  3. Generate Preview (if applicable) │ │
│  │  4. Extract Metadata                 │ │
│  └──────────────────────────────────────┘ │
└─────────────────────┬─────────────────────┘
                      │
┌─────────────────────▼─────────────────────┐
│              User Response                │
│     "Created financial_report.pdf..."     │
│         + Complete Artifact Object        │
└───────────────────────────────────────────┘
```

## Data Types

### MuxiArtifact
The core artifact data type containing:

```python
@dataclass
class MuxiArtifact:
    type: str              # "chart", "document", "code", "image", "text", "data"
    format: str            # File extension: "png", "pdf", "py"
    filename: str          # Original filename
    content: Optional[str] # Raw text content (for text files)
    data_url: str          # Base64 data URL with MIME type
    metadata: ArtifactMetadata
    preview: Optional[ArtifactPreview] = None
    id: Optional[str] = None
```

### ArtifactMetadata
Detailed metadata about the artifact:

```python
@dataclass
class ArtifactMetadata:
    size_bytes: int
    created_at: datetime
    lines: Optional[int] = None      # For text files
    characters: Optional[int] = None  # For text files
    language: Optional[str] = None    # Programming language
    pages: Optional[int] = None       # For documents
    width: Optional[int] = None       # For images
    height: Optional[int] = None      # For images
```

### ArtifactPreview
Preview information for visual files:

```python
@dataclass
class ArtifactPreview:
    thumbnail: Optional[str] = None   # Base64 PNG thumbnail
```

## File Generation Capabilities

### Supported File Types

#### 📊 **Charts and Visualizations**
- Bar charts, line graphs, pie charts
- Scatter plots, heatmaps
- Custom matplotlib/seaborn visualizations
- Interactive plotly charts

#### 📄 **Documents**
- PDF reports with reportlab
- Word documents (.docx)
- PowerPoint presentations (.pptx)
- Markdown files

#### 📈 **Data Files**
- CSV datasets
- JSON configurations
- Excel spreadsheets (.xlsx)
- YAML configurations

#### 🖼️ **Images**
- PNG, JPEG, GIF
- QR codes and barcodes
- Custom PIL/Pillow images
- SVG graphics
- **PDF Preview Thumbnails** (requires Poppler - see requirements)

#### 💻 **Code Files**
- Python scripts
- JavaScript modules
- HTML/CSS files
- Configuration files

### Security Features

#### Whitelisted Imports
Only safe, approved libraries are allowed:

```python
ALLOWED_IMPORTS = {
    # Data processing
    "pandas", "numpy", "scipy",
    # Visualization
    "matplotlib", "seaborn", "plotly",
    # Documents
    "reportlab", "python-docx", "python-pptx",
    # Images
    "PIL", "Pillow", "qrcode",
    # Standard library (safe subset)
    "json", "csv", "datetime", "math", "random"
}
```

#### Execution Limits
- **Memory**: 512MB maximum (Linux only - no limit on macOS/Windows)
- **Time**: 30 seconds maximum
- **File Size**: 100MB output directory limit
- **Network**: No external network access

> **Note**: Memory limits using `ulimit -v` only work on Linux. macOS and Windows run without memory limits but still have timeout protection.

#### Code Validation
AST-based validation prevents:
- Dangerous function calls (exec, eval, etc.)
- System access (os.system, subprocess)
- Import restrictions
- Global/nonlocal modifications

## System Requirements

### Python Dependencies
All required Python packages are included in the core dependencies:
- `reportlab` - PDF generation
- `fpdf2` - Alternative PDF generation
- `pdf2image` - PDF preview generation (requires Poppler)
- `Pillow` - Image processing and thumbnail generation
- `python-docx` - Word document generation
- `openpyxl` - Excel file generation
- `matplotlib`, `seaborn`, `plotly` - Data visualization

### System Dependencies for PDF Previews

**PDF preview thumbnail generation requires Poppler utilities to be installed:**

#### macOS
```bash
brew install poppler
```

#### Ubuntu/Debian
```bash
sudo apt-get install poppler-utils
```

#### RHEL/CentOS/Fedora
```bash
sudo yum install poppler-utils
```

#### Windows
Download and install Poppler for Windows from: https://blog.alivate.com.au/poppler-windows/

> **Note**: If Poppler is not installed, PDF files will still be generated successfully, but the `preview` field will be `null`. All other functionality remains unaffected.

## Usage Examples

### Basic File Generation

```python
# Agent conversation
response = await overlord.chat(
    "Create a simple bar chart showing Q1=100, Q2=150, Q3=120",
    session_id="user123"
)

# Check for artifacts
if response.artifacts:
    chart = response.artifacts[0]
    print(f"Created: {chart.filename}")
    print(f"Type: {chart.type}")
    print(f"Data URL: {chart.data_url[:50]}...")
```

### Advanced Document Generation

```python
response = await overlord.chat(
    """Create a professional report with:
    1. Title page with company logo
    2. Executive summary
    3. Data analysis with charts
    4. Conclusions and recommendations
    Save as quarterly_report.pdf""",
    session_id="business_user"
)
```

### Multi-File Generation

```python
response = await overlord.chat(
    """Create a web dashboard:
    1. index.html with chart container
    2. style.css for styling
    3. data.json with sample data
    4. chart.js for interactive charts""",
    session_id="web_dev"
)

# Multiple artifacts will be returned
for artifact in response.artifacts:
    print(f"- {artifact.filename} ({artifact.format})")
    print(f"  Size: {artifact.metadata.size_bytes} bytes")
    if artifact.preview and artifact.preview.thumbnail:
        print(f"  Has preview: Yes")
```

## Storage and Retrieval

### Session-Based Organization

```python
from muxi.runtime.formation.artifacts.storage import (
    store_artifact, get_recent_artifacts
)

# Store an artifact
artifact_id = store_artifact(
    session_id="user123",
    artifact=my_artifact,
    user_id="alice"
)

# Retrieve recent artifacts
recent = get_recent_artifacts(
    session_id="user123",
    max_age_minutes=60
)
```

### ID Format
Artifacts use nanoid-based IDs with 3-letter prefixes:
- **art_**: Regular artifacts (`art_Kx9mN2pQw8R5`)
- **exe_**: Execution tracking (`exe_m4nB7tY2`)

### Cleanup
Automatic cleanup removes:
- Artifacts older than 60 minutes (configurable)
- Excessive files when storage limit reached
- Temporary execution files

## Configuration

### Artifact Service Configuration

The artifact service is automatically initialized when the Overlord starts. Configuration options are defined in the service itself:

```python
# In artifact_service.py
MAX_EXECUTION_TIME = 30      # Maximum execution time in seconds
MAX_OUTPUT_SIZE_MB = 100     # Maximum output directory size
MAX_MEMORY_MB = 512          # Memory limit (Linux only)
```

### Agent System Message

```yaml
agents:
  - id: "designer"
    name: "Design Assistant"
    system_message: |
      You are a design assistant. When users ask for visual content,
      use the generate_file tool to create charts, diagrams, or images.
      Always provide clear filenames and descriptions.
```

## API Reference

### Core Functions

#### `extract_artifacts_from_tool_results(tool_results)`
Extracts artifacts from MCP tool execution results.

**Parameters:**
- `tool_results`: List of tool execution results

**Returns:**
- `List[MuxiArtifact]`: Extracted artifacts

#### `store_artifact(session_id, artifact, user_id)`
Stores an artifact in the session-based storage.

**Parameters:**
- `session_id`: Session identifier
- `artifact`: MuxiArtifact object
- `user_id`: User identifier

**Returns:**
- `str`: Generated artifact ID

#### `get_recent_artifacts(session_id, max_age_minutes=60)`
Retrieves recent artifacts for a session.

**Parameters:**
- `session_id`: Session identifier
- `max_age_minutes`: Maximum age filter

**Returns:**
- `List[MuxiArtifact]`: Recent artifacts

### Agent Tool: generate_file

The `generate_file` tool is automatically available to agents when the artifact service is initialized.

#### Function Signature
```python
async def generate_file(code: str, filename: Optional[str] = None) -> MuxiArtifact
```

#### Parameters
- `code`: Python code to execute for file generation
- `filename`: Optional filename hint for the generated file

#### Returns
A `MuxiArtifact` object containing:
- Complete base64 data URL of the generated file
- File metadata (size, creation time, dimensions for images)
- Preview thumbnail for supported formats (images, PDFs with Poppler)
- File type classification

#### Integration
The tool is integrated directly with agents through the Overlord:
```python
# In agent.py
if tool_name == "generate_file" and self.overlord and hasattr(self.overlord, "artifact_service"):
    artifact = await self.overlord.artifact_service.generate_file(code, filename)
    # Artifact is automatically attached to the response
```

#### Example Usage
```python
# Create a chart
result = await mcp_client.call_tool("generate_file", {
    "code": """
import matplotlib.pyplot as plt
import numpy as np

x = ['Q1', 'Q2', 'Q3', 'Q4']
y = [100, 150, 120, 180]

plt.figure(figsize=(10, 6))
plt.bar(x, y, color='skyblue')
plt.title('Quarterly Sales')
plt.ylabel('Revenue ($K)')
plt.savefig('quarterly_sales.png', dpi=300, bbox_inches='tight')
plt.close()
"""
})
```

## Error Handling

### Common Errors

#### Code Validation Errors
```python
# Error: Import not allowed
ValidationError: "Import not allowed: os"

# Error: Function not allowed
ValidationError: "Function not allowed: exec"
```

#### Execution Errors
```python
# Error: Memory limit exceeded
RuntimeError: "Memory limit exceeded (max 512MB)"

# Error: Timeout
RuntimeError: "Code execution timed out after 30 seconds"
```

#### File System Errors
```python
# Error: Permission denied
RuntimeError: "Permission denied: cannot write to /system/"

# Error: Disk space
RuntimeError: "Output directory size limit exceeded"
```

### Error Recovery
The system provides automatic error recovery:
- Retry failed operations
- Fallback to alternative approaches
- Clear error messages for debugging

## Best Practices

### Code Generation
```python
# Good: Clear, focused code
code = """
import matplotlib.pyplot as plt
data = [1, 2, 3, 4, 5]
plt.plot(data)
plt.savefig('chart.png')
"""

# Bad: Complex, multi-purpose code
code = """
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
# ... 50+ lines of complex logic
"""
```

### File Naming
```python
# Good: Descriptive names
"quarterly_sales_2024.png"
"customer_analysis_report.pdf"

# Bad: Generic names
"chart.png"
"report.pdf"
```

### Error Handling
```python
try:
    response = await overlord.chat("Create a chart...")
    if response.artifacts:
        chart = response.artifacts[0]
        # Process chart
    else:
        # Handle no artifacts case
except Exception as e:
    # Handle errors gracefully
    logger.error(f"Artifact generation failed: {e}")
```

## Performance Considerations

### Optimization Tips
- Use efficient libraries (pandas vs pure Python)
- Optimize chart resolution for file size
- Implement caching for repeated operations
- Clean up temporary files promptly

### Resource Management
- Monitor memory usage during generation
- Set appropriate timeout values
- Implement file size limits
- Use streaming for large files

## Security Considerations

### Sandboxing
- All code executes in isolated subprocess
- No access to system resources
- Whitelisted imports only
- Memory and time limits enforced

### File System Security
- Restricted to outputs directory
- No ability to read sensitive files
- Automatic cleanup of temporary files
- Path traversal prevention

### User Isolation
- Session-based artifact storage
- User-specific credential handling
- No cross-user data access
- Audit trail maintenance

## Testing

### Unit Tests
```python
async def test_artifact_creation():
    artifact = MuxiArtifact(
        type="chart",
        format="png",
        filename="test.png",
        content="test data",
        data_url="data:image/png;base64,..."
    )

    artifact_id = store_artifact("test_session", artifact, "test_user")
    assert artifact_id.startswith("art_")
```

### Integration Tests
```python
async def test_file_generation_e2e():
    response = await overlord.chat(
        "Create a simple bar chart",
        session_id="test_session"
    )

    assert response.artifacts
    assert len(response.artifacts) == 1
    assert response.artifacts[0].format == "png"
```

## Troubleshooting

### Common Issues

#### No Artifacts Generated
1. Check if artifact service is initialized in Overlord
2. Verify code validation passes (check for forbidden imports)
3. Ensure proper file saving in code
4. Check execution logs for errors

#### PDF Preview Not Generated
1. Install Poppler utilities (see System Requirements)
2. Check logs for "PDF thumbnail generation failed"
3. Verify PDF is valid and not corrupted
4. Preview will be `null` without Poppler (this is normal)

#### Memory Limit Errors on macOS
1. Memory limits using `ulimit -v` don't work on macOS
2. The service automatically skips memory limits on macOS/Windows
3. Timeout protection still applies (30 seconds default)

#### File Not Found
1. Verify output directory exists (`/tmp/muxi_artifacts/`)
2. Check file permissions
3. Ensure proper file path in code
4. Check for cleanup timing issues

#### Performance Issues
1. Optimize code complexity
2. Reduce file sizes
3. Check execution timeout (30s limit)
4. Monitor output directory size (100MB limit)

### Debug Mode
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Or via environment
export MUXI_LOG_LEVEL=DEBUG
```

---

The artifacts system provides a powerful, secure, and flexible foundation for AI agents to create and manage files. Its sandboxed execution environment, intelligent tracking, and comprehensive metadata make it ideal for production AI systems that need to generate real-world deliverables.
