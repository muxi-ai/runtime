#!/usr/bin/env python3
"""
Allowed libraries for file generation MCP
This list should be provided to the LLM to ensure it only uses available libraries
"""

# Core Python libraries (always available)
CORE_LIBRARIES = [
    'base64',
    'csv',
    'datetime',
    'io',
    'json',
    'math',
    'os',
    'random',
    're',
    'string',
    'time',
]

# Data processing and analysis
DATA_LIBRARIES = [
    'pandas',
    'numpy',
    'openpyxl',  # Excel file handling
]

# Visualization libraries
VISUALIZATION_LIBRARIES = [
    'matplotlib',
    'seaborn',
    'plotly',
    'bokeh',
]

# Document generation libraries
DOCUMENT_LIBRARIES = [
    'docx',  # Word documents
    'reportlab',  # PDF generation
    'markdown',
    'pptx',  # PowerPoint presentations
]

# Web/Interactive libraries (expanded based on suggestion)
WEB_LIBRARIES = [
    'dash',  # Interactive dashboards
    'streamlit',  # Web apps
    'flask',  # Web framework
]

# All allowed libraries combined
ALLOWED_LIBRARIES = (
    CORE_LIBRARIES +
    DATA_LIBRARIES +
    VISUALIZATION_LIBRARIES +
    DOCUMENT_LIBRARIES +
    WEB_LIBRARIES
)

# Library descriptions for LLM context
LIBRARY_DESCRIPTIONS = {
    # Data processing
    'pandas': 'Data manipulation and analysis',
    'numpy': 'Numerical computing',
    'openpyxl': 'Excel file reading/writing',
    
    # Visualization
    'matplotlib': 'Static plotting and charts',
    'seaborn': 'Statistical data visualization',
    'plotly': 'Interactive plots and charts',
    'bokeh': 'Interactive visualization',
    
    # Documents
    'docx': 'Create Word documents',
    'reportlab': 'Create PDF documents',
    'pptx': 'Create PowerPoint presentations',
    
    # Web/Interactive
    'dash': 'Interactive web dashboards',
    'streamlit': 'Data apps and dashboards',
    'flask': 'Web applications',
}

def get_allowed_libraries_prompt():
    """Generate a prompt section describing allowed libraries"""
    prompt = """
You have access to the following Python libraries for file generation:

**Data Processing:**
- pandas: Data manipulation and analysis
- numpy: Numerical computing
- openpyxl: Excel file reading/writing
- csv, json: Built-in data formats

**Visualization:**
- matplotlib: Static plotting and charts
- seaborn: Statistical data visualization
- plotly: Interactive plots and charts
- bokeh: Interactive visualization

**Document Generation:**
- docx: Create Word documents
- reportlab: Create PDF documents
- pptx: Create PowerPoint presentations
- markdown: Markdown processing

**Web/Interactive:**
- dash: Interactive web dashboards
- streamlit: Data apps and dashboards
- flask: Web applications

**Standard Libraries:**
- base64, io, datetime, time, random, re, string, math, os

Please only use these libraries in your code. If a requested feature requires a library not in this list, 
use the closest available alternative or implement a workaround using the allowed libraries.
"""
    return prompt

if __name__ == "__main__":
    print("Allowed Libraries for File Generation MCP:")
    print("=" * 50)
    for lib in sorted(ALLOWED_LIBRARIES):
        desc = LIBRARY_DESCRIPTIONS.get(lib, "Standard library")
        print(f"- {lib}: {desc}")
    print(f"\nTotal: {len(ALLOWED_LIBRARIES)} libraries")