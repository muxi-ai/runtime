# File Generation with Built-in MCP

MUXI Runtime includes a built-in File Generation MCP (Model Context Protocol) server that enables agents to create various types of files including charts, documents, spreadsheets, images, and presentations.

## Overview

The File Generation MCP allows agents to:
- Generate data visualizations (charts, graphs, plots)
- Create documents (Word, PDF, Markdown)
- Export data to spreadsheets (Excel, CSV)
- Generate images and diagrams
- Create presentations
- Generate QR codes and barcodes

All file generation happens in a secure, sandboxed environment with strict library whitelisting.

## Configuration

### Enabling File Generation

By default, all built-in MCPs are enabled. You can control this behavior in your `formation.afs`:

```yaml
# Enable all built-in MCPs (default)
runtime:
  built_in_mcps: true

# Disable all built-in MCPs
runtime:
  built_in_mcps: false

# Enable only specific MCPs (granular control)
runtime:
  built_in_mcps:
    - file-generation
    # - web-search  # Future MCP
    # - database    # Future MCP
```

### Installing Dependencies

The file generation libraries are optional dependencies. Install them with:

```bash
pip install muxi[file-generation]
```

Or install specific libraries as needed:

```bash
# For charts and visualizations
pip install matplotlib seaborn plotly

# For documents
pip install python-docx reportlab fpdf2

# For spreadsheets
pip install pandas openpyxl xlsxwriter

# For images
pip install Pillow qrcode

# For presentations
pip install python-pptx
```

## Usage Examples

Once enabled, agents can generate files in response to user requests:

### Creating Charts

```
User: Create a bar chart showing monthly sales data for 2024
Agent: I'll create a bar chart showing the monthly sales data for 2024.

[Agent generates a bar chart using matplotlib]
File generated successfully: monthly_sales_2024.png
```

### Generating Documents

```
User: Create a report summarizing our Q4 performance
Agent: I'll create a comprehensive Q4 performance report for you.

[Agent generates a Word document with formatted text, tables, and sections]
File generated successfully: Q4_Performance_Report.docx
```

### Exporting Data

```
User: Export this data to an Excel file with charts
Agent: I'll create an Excel file with your data and include relevant charts.

[Agent creates an Excel file with multiple sheets and embedded charts]
File generated successfully: data_export.xlsx
```

### Creating QR Codes

```
User: Generate a QR code for our website URL
Agent: I'll generate a QR code for your website URL.

[Agent creates a QR code image]
File generated successfully: website_qr_code.png
```

## Supported File Types

### Visualizations
- PNG charts (matplotlib, seaborn)
- Interactive HTML charts (plotly)
- Statistical plots
- Heatmaps and correlation matrices

### Documents
- Word documents (.docx)
- PDF files
- Markdown files
- HTML reports

### Spreadsheets
- Excel files (.xlsx) with formatting
- CSV files
- Multi-sheet workbooks
- Embedded charts in Excel

### Images
- PNG/JPEG images
- QR codes
- Barcodes
- Diagrams and flowcharts

### Presentations
- PowerPoint files (.pptx)
- Slides with text, images, and charts

## Security Features

The File Generation MCP includes several security measures:

1. **Library Whitelisting**: Only approved Python libraries can be imported
2. **Sandboxed Execution**: Code runs in a subprocess with limited permissions
3. **Timeout Protection**: 30-second maximum execution time
4. **Output Isolation**: Files can only be created in the designated outputs directory
5. **No Network Access**: Generated code cannot make network requests
6. **Environment Sanitization**: Sensitive environment variables are removed

## Output Directory

Generated files are saved in an `outputs/` directory relative to where MUXI is running. The system automatically:
- Creates the directory if it doesn't exist
- Cleans up old files when the directory exceeds 100MB
- Returns the full path to generated files

## Troubleshooting

### Missing Libraries

If you get an error about missing libraries:
```bash
pip install muxi[file-generation]
```

### File Not Generated

Common causes:
- Code syntax errors
- Missing required imports
- File not explicitly saved in the code
- Execution timeout (for complex operations)

### Permission Errors

Ensure the MUXI process has write permissions to create the `outputs/` directory.

## Advanced Usage

### Custom Configurations

Agents can be given specific instructions for file generation:

```yaml
agents:
  - id: data-analyst
    name: Data Analyst
    description: Specializes in data visualization and reporting
    system_message: |
      When creating charts:
      - Always use a professional color scheme
      - Include proper labels and titles
      - Save high-resolution images (300 DPI)
      - Prefer interactive plotly charts for web display
```

### Integration with Other Services

The File Generation MCP works seamlessly with other MUXI features:
- Memory systems can store references to generated files
- A2A communication can share file paths between agents
- Webhook notifications can include generated file information

## Best Practices

1. **Clear Filenames**: Agents should use descriptive filenames
2. **Error Handling**: Include try-except blocks in generated code
3. **Resource Efficiency**: Generate files only when needed
4. **File Formats**: Choose appropriate formats for the use case
5. **Documentation**: Include comments in generated code

## Limitations

- Maximum execution time: 30 seconds
- Output directory size limit: 100MB (auto-cleanup)
- No network access during file generation
- Limited to whitelisted Python libraries
- Single file output per generation (newest file is returned)

## Future Enhancements

Planned improvements include:
- Multi-file generation support
- File preview generation
- Caching for frequently requested files
- Template-based generation
- Additional output formats
