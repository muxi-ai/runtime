# MUXI Runtime: Agent Knowledge System

## Overview

The MUXI Runtime Knowledge System enables agents to access and search through domain knowledge sources, augmenting their responses with relevant information. It provides a hybrid architecture combining disk-based caching with in-memory vector search for optimal performance and cost efficiency.

## Key Features

- **Multiple File Format Support**: Handles 30+ file formats including documents, PDFs, images, audio, and more via MarkItDown
- **Smart Caching**: MD5-based change detection prevents unnecessary embedding regeneration
- **Namespace Isolation**: Knowledge is protected from memory pressure with dedicated namespace
- **Formation-Specific Storage**: Each formation has isolated knowledge storage
- **Incremental Updates**: Only changed files regenerate embeddings
- **Semantic Search**: Vector-based search using FAISS for fast retrieval

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
│  Disk Cache     │ ←→  │ ShortTermMemory  │
│ (JSON files)    │     │    (FAISS)       │
└─────────────────┘     └──────────────────┘
```

### Components

1. **FileKnowledge**: Loads content from files and directories
2. **DocumentChunkManager**: Intelligently chunks documents for embedding
3. **KnowledgeHandler**: Orchestrates loading, caching, and searching
4. **ShortTermMemory**: Provides vector search via FAISS
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
        - path: "docs/api-reference.md"
          description: "API documentation"
        - path: "knowledge/"
          description: "Knowledge base directory"
```

### Advanced Configuration

```yaml
agents:
  - id: "advanced-agent"
    name: "Advanced Knowledge Agent"
    knowledge:
      enabled: true
      sources:
        - path: "/absolute/path/to/docs"
          description: "External documentation"
          recursive: true
          allowed_extensions: [".md", ".txt", ".pdf"]
          max_files: 100
          max_file_size: 5242880  # 5MB
```

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
4. Populate ShortTermMemory with embeddings
```

### 2. Incremental Updates
```
1. On formation restart:
   - Compare current files with cached metadata
   - Remove embeddings for deleted files
   - Skip unchanged files (same MD5)
   - Regenerate only for new/modified files
2. Update ShortTermMemory incrementally
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
Knowledge uses the `"knowledge"` namespace in ShortTermMemory, protected from FIFO eviction which only affects the `"buffer"` namespace.

### Knowledge Injection
Search results can be temporarily injected into memory using the `"knowledge_injection"` namespace for context enhancement.

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

### Speed Improvements
- **Before**: 30-60 seconds for full regeneration
- **After**: <5 seconds for cache loading

### Best Practices
1. **Chunk Size**: Let DocumentChunkManager handle adaptive chunking
2. **File Limits**: Set reasonable `max_files` and `max_file_size`
3. **File Organization**: Group related content in directories
4. **Descriptions**: Provide clear descriptions for each source

## Error Handling

The knowledge system gracefully handles various error scenarios:

1. **Missing Files**: Logged and skipped
2. **Embedding Failures**: Individual chunks skipped, others processed
3. **Cache Corruption**: Regenerates from source
4. **Memory Pressure**: Knowledge protected from eviction

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

1. **File Size**: Default 1MB limit per file (configurable)
2. **File Count**: Default 50 files per source (configurable)
3. **Embedding Model**: Uses formation's configured text model
4. **Vector Dimensions**: Must match embedding model (typically 1536)

## Future Enhancements

1. **Compression**: Compress cache files for large knowledge bases
2. **TTL**: Time-based cache expiration
3. **Versioning**: Track embedding model versions
4. **Parallel Processing**: Generate embeddings in parallel
5. **Remote Sources**: Support for URLs and APIs

## Troubleshooting

### Knowledge Not Loading
- Check `knowledge.enabled: true` in configuration
- Verify file paths exist and are readable
- Check formation logs for error messages

### Search Not Working
- Ensure embedding function is provided
- Verify knowledge was loaded successfully
- Check if formation has required LLM models configured

### High Memory Usage
- Reduce `max_files` limit
- Use `max_file_size` to skip large files
- Enable more aggressive FIFO cleanup

### Stale Results
- Delete cache directory to force regeneration
- Check if source files have actually changed
- Verify MD5 hashing is working correctly
