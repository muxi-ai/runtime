# MUXI Runtime: Agent Knowledge System

## Overview

The MUXI Runtime Knowledge System enables agents to access and search through domain knowledge sources, augmenting their responses with relevant information. It provides a hybrid architecture combining disk-based caching with in-memory vector search for optimal performance and cost efficiency.

## Key Features

- **Multiple File Format Support**: Handles 30+ file formats including documents, PDFs, images, audio, and more via MarkItDown
- **Smart Caching**: MD5-based change detection prevents unnecessary embedding regeneration (45% cache hit rate in testing)
- **Agent-Level Isolation**: Complete knowledge isolation between agents - each agent only sees its configured sources
- **Namespace Isolation**: Knowledge is protected from memory pressure with dedicated namespace
- **Formation-Specific Storage**: Each formation has isolated knowledge storage
- **Incremental Updates**: Only changed files regenerate embeddings
- **Semantic Search**: Vector-based search using FAISS for fast retrieval
- **Lazy Initialization**: Knowledge only loaded when first query requires it

## Architecture

```
Formation Config
    ↓
FileKnowledge Sources
    ↓
DocumentChunkManager (adaptive chunking)
    ↓
LLM Embeddings API
    ↓
┌─────────────────┐     ┌──────────────────┐
│  Disk Cache     │ ←→  │ WorkingMemory  │
│ (JSON files)    │     │    (FAISS)       │
└─────────────────┘     └──────────────────┘
```

### Components

1. **FileKnowledge**: Loads content from files and directories
2. **DocumentChunkManager**: Intelligently chunks documents for embedding
3. **KnowledgeHandler**: Orchestrates loading, caching, and searching
4. **WorkingMemory**: Provides vector search via FAISS
5. **Disk Cache**: Persists embeddings to avoid regeneration

## Configuration

### Basic Configuration

```yaml
agents:
  - id: "my-agent"
    name: "Knowledge Agent"
    knowledge:
      enabled: true
      sources:
        - path: "knowledge/api-reference.md"
          description: "API documentation"
        - path: "knowledge/docs/"
          description: "Knowledge base directory"
```

### Alternative Formats

The knowledge field supports multiple formats:

```yaml
# Option 1: Dict format with enabled flag (recommended)
knowledge:
  enabled: true
  sources:
    - path: "knowledge/docs/"

# Option 2: Empty/disabled - just omit the field entirely
# (no knowledge field)

# Option 3: Empty list (valid, no knowledge loaded)
knowledge: []
```

**Path Rules:**
- All paths must be relative to formation directory root
- Absolute paths (starting with `/`) are rejected
- Parent directory traversal (`..`) is rejected
- Recommended: Keep knowledge in `knowledge/` subdirectory
- Files can be anywhere within formation directory

### Advanced Configuration

```yaml
agents:
  - id: "advanced-agent"
    name: "Advanced Knowledge Agent"
    knowledge:
      enabled: true
      embed_batch_size: 50      # For large knowledge bases
      max_files_per_source: 10  # Limit files per directory (default: 5)
      sources:
        - path: "knowledge/manuals/"
          description: "Product manuals"
          recursive: true
          allowed_extensions: [".md", ".txt", ".pdf"]
          file_limit: 20        # Override max_files_per_source for this source
          max_file_size: 5242880  # 5MB
        - path: "docs/api/"
          description: "API docs (can be anywhere in formation)"
```

**Security:** Knowledge sources are confined to the formation directory for portability and security. Future versions will support remote sources (S3, HTTP) that are downloaded during deployment.

## Supported File Formats

### Text Formats
- `.txt` - Plain text files
- `.md` - Markdown documents

### Documents (via MarkItDown)
- `.docx` - Microsoft Word documents
- `.pptx` - PowerPoint presentations
- `.xlsx`, `.xls` - Excel spreadsheets
- `.pdf` - PDF documents
- `.epub` - E-books

### Multimedia (with extraction)
- `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff` - Images (OCR support)
- `.wav`, `.mp3` - Audio files (transcription support)

### Web & Data
- `.html`, `.htm` - Web pages
- `.csv` - Comma-separated values
- `.json` - JSON data
- `.xml` - XML documents
- `.zip` - Archives (contents extracted)

## Knowledge Loading Process

### 1. Initial Load
```
1. Formation loads agent configuration
2. KnowledgeHandler discovers configured sources
3. For each file:
   - Check disk cache by MD5 hash
   - If cached: Load embeddings from disk
   - If not cached: Generate embeddings and save to cache
4. Populate WorkingMemory with embeddings
```

### 2. Incremental Updates
```
1. On formation restart:
   - Compare current files with cached metadata
   - Remove embeddings for deleted files
   - Skip unchanged files (same MD5)
   - Regenerate only for new/modified files
2. Update WorkingMemory incrementally
```

## Cache Management

### Cache Location
```
~/.muxi/{formation_id}/cache/knowledge/{md5_hash}.cache
```

### Cache Format
```json
{
  "source_hash": "abc123...",
  "source_path": "/path/to/file.md",
  "chunks": [
    {
      "content": "chunk text...",
      "embedding": [0.1, 0.2, ...],
      "metadata": {
        "document_id": "...",
        "chunk_id": "...",
        "source": "/path/to/file.md",
        "content_hash": "md5_hash"
      }
    }
  ]
}
```

## Memory Management

### Namespace Protection
Knowledge uses the `"knowledge"` namespace in WorkingMemory, protected from FIFO eviction which only affects the `"buffer"` namespace.

### Knowledge Injection
Search results can be temporarily injected into memory using the `"knowledge_injection"` namespace for context enhancement.

## Agent Knowledge Isolation

### Complete Isolation
Each agent has complete isolation of its knowledge sources:
- Agents cannot access knowledge configured for other agents
- Knowledge embeddings are namespaced by agent ID
- No cross-contamination between agent knowledge bases

### Cross-Agent Knowledge via Overlord
While agents are isolated, the Overlord can coordinate cross-agent queries:

```yaml
# Agent 1: Support agent with FAQ knowledge
agents:
  - id: "support"
    knowledge:
      sources:
        - path: "knowledge/faq/"
          description: "Support FAQs"

# Agent 2: Sales agent with pricing knowledge
  - id: "sales"
    knowledge:
      sources:
        - path: "knowledge/pricing/"
          description: "Pricing information"

# User query: "What's the pricing for the FAQ features?"
# Overlord routes to both agents and combines responses
```

## Usage Examples

### Basic Knowledge Search

```python
# In an agent's process_request method
async def process_request(self, request):
    # Search knowledge base
    if self.knowledge_handler:
        results = await self.knowledge_handler.search(
            query=request.content,
            top_k=5,
            generate_embeddings_fn=self.model.generate_embeddings
        )

        # Use results to enhance response
        context = "\n".join([r["content"] for r in results])
        enhanced_prompt = f"Context:\n{context}\n\nQuery: {request.content}"
```

### Unified Search (Knowledge + Memory)

```python
# Search both knowledge and conversation memory
results = await self.knowledge_handler.unified_search(
    query="API authentication",
    knowledge_top_k=3,
    memory_top_k=2,
    include_knowledge=True,
    include_memory=True
)

# Results structure:
# {
#   "knowledge": [...],  # From knowledge sources
#   "memory": [...]      # From conversation history
# }
```

## Performance Optimization

### Cost Savings
- **Before**: Every restart regenerated all embeddings (~$0.10-0.50)
- **After**: Only changed files regenerate (typically $0)
- **Test Results**: 45% cache hit rate, 9 out of 20 files cached in large knowledge base test

### Speed Improvements
- **Before**: 30-60 seconds for full regeneration
- **After**: <5 seconds for cache loading
- **Test Results**:
  - Formation load: ~1.14 seconds with 20 knowledge files
  - First query: ~12 seconds (includes knowledge initialization)
  - Subsequent queries: ~9 seconds

### Best Practices
1. **Chunk Size**: Let DocumentChunkManager handle adaptive chunking
2. **File Limits**: Set reasonable `max_files` and `max_file_size`
3. **File Organization**: Group related content in directories
4. **Descriptions**: Provide clear descriptions for each source

## Error Handling

The knowledge system gracefully handles various error scenarios:

1. **Missing Files**: Logged and skipped, formation continues loading
2. **Empty Directories**: Handled gracefully, agent functions normally
3. **Unsupported File Types**: Silently filtered (e.g., .bin, .exe, .jpg)
4. **Large Knowledge Bases**: File limits prevent overload (max_files_per_source)
5. **Embedding Failures**: Individual chunks skipped, others processed
6. **Cache Corruption**: Regenerates from source
7. **Memory Pressure**: Knowledge protected from eviction

## Observability

All knowledge operations emit observability events:

```python
# Success events
SystemEvents.KNOWLEDGE_SOURCE_LOADED
ConversationEvents.CONTENT_PROCESSED

# Error events
SystemEvents.KNOWLEDGE_SOURCE_FAILED
ErrorEvents.INTERNAL_ERROR
```

## Limitations

1. **File Size**: Default 1MB limit per file (configurable via `max_file_size`)
2. **File Count**: Default 5 files per source (configurable via `max_files_per_source`)
3. **Embedding Model**: Uses formation's configured text model
4. **Vector Dimensions**: Must match embedding model (typically 1536 for OpenAI)
5. **Agent Isolation**: Agents cannot share knowledge directly
6. **Lazy Loading**: Knowledge only loads on first query, not at startup

## Future Enhancements

1. **Compression**: Compress cache files for large knowledge bases
2. **TTL**: Time-based cache expiration
3. **Versioning**: Track embedding model versions
4. **Parallel Processing**: Generate embeddings in parallel
5. **Remote Sources**: Support for URLs and APIs

## Common Pitfalls & Solutions

### Directory Loading Issues
- **Problem**: Directory not loading when `file_limit=1`
- **Solution**: file_limit applies after directory traversal, not before

### Missing MarkItDown Support
- **Problem**: PDFs and documents showing as binary
- **Solution**: System uses MarkItDown automatically via `_process_file`

### Embedding Function Not Available
- **Problem**: Knowledge search fails with "no embedding function"
- **Solution**: Store embedding function during initialization: `handler.embed_fn = agent._embed_fn`

### Knowledge Not Updating
- **Problem**: Changes to files not reflected
- **Solution**: Check MD5 hashing is working; delete cache to force regeneration

## Troubleshooting

### Knowledge Not Loading
- Check `knowledge.enabled: true` in configuration
- Verify file paths exist and are readable
- Check formation logs for error messages
- Ensure paths use forward slashes, even on Windows

### Search Not Working
- Ensure embedding function is provided
- Verify knowledge was loaded successfully
- Check if formation has required LLM models configured
- Confirm agent has been queried at least once (lazy loading)

### High Memory Usage
- Reduce `max_files_per_source` limit (default: 5)
- Use `file_limit` on specific sources
- Use `max_file_size` to skip large files
- Enable more aggressive FIFO cleanup

### Stale Results
- Delete cache directory to force regeneration: `~/.muxi/{formation_id}/cache/knowledge/`
- Check if source files have actually changed
- Verify MD5 hashing is working correctly
- Look for cache files with old timestamps
