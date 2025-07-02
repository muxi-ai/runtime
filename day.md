# Test Preparation Inventory

This document provides a complete inventory of everything needed to run the MUXI Runtime Comprehensive Test Plan.

## 🚀 Quick Start Checklist

- [ ] PostgreSQL installed and running
- [ ] FAISSx servers available (ports 45678, 65432)
- [ ] API keys configured in secrets.enc
- [ ] Test files prepared (videos, audio, PDFs)
- [ ] Python dependencies installed
- [ ] Test formations verified

## 1. External Services

### Databases
- [ ] **PostgreSQL**
  - URL: `postgresql://localhost/muxi_test`
  - Used for: Multi-user memory, credentials, scheduler
  - Start: `pg_ctl start -D /usr/local/var/postgresql`

- [ ] **SQLite**
  - Path: `sqlite:///knowledge_test.db`
  - Used for: Single-user memory tests
  - Note: Auto-created, no setup needed

### Vector Search Servers
- [ ] **FAISSx (Port 45678)**
  - No authentication
  - Start: `python -m faissx.server --port 45678 --no-auth`
  - Requires: `FAISSX_TENANT_ID` in secrets

- [ ] **FAISSx (Port 65432)**
  - With authentication
  - Start: `python -m faissx.server --port 65432 --auth`
  - Requires: Auth credentials + tenant ID

### Communication Servers
- [ ] **A2A Registry Server**
  - Start: `python -m muxi.runtime.services.a2a.registry`
  - Used for: Agent-to-agent communication

### MCP Servers
- [ ] Built-in File Generation MCP (auto-starts)
- [ ] External MCPs as needed:
  - Filesystem MCP
  - Web search MCP
  - Gmail MCP
  - Database MCP
  - Stock API MCP

### Test Infrastructure
- [ ] **Webhook Server**
  - URL: `http://localhost:8080/webhook`
  - Start: `python -m muxi.runtime.tests.webhook_server`
  - Used for: Async operation testing

## 2. Test Files Required

### Video Files (test-files/)
- [ ] `small_video_5mb.mp4` - Direct processing test
- [ ] `presentation_127mb.mp4` - Chunked processing test
- [ ] `iphone_launch_86mb.mov` - Timeout testing
- [ ] `training_video_500mb.mp4` - Memory efficiency test
- [ ] `corrupted_video.mp4` - Error handling test

### Audio Files (test-files/)
- [ ] `podcast_150mb.mp3` - Large audio chunking
- [ ] `conference_call_45mb.m4a` - >25MB Whisper limit test
- [ ] `podcast_2hour.mp3` - Long duration processing
- [ ] `presentation_with_music.mp3` - Mixed content test

### Document Files (test-files/)
- [ ] `annual_report_500pages.pdf` - Large PDF processing
- [ ] `technical_manual_300pages.pdf` - Section detection test
- [ ] `doc1_100pages.pdf` - Multi-document test 1
- [ ] `doc2_150pages.pdf` - Multi-document test 2
- [ ] `doc3_200pages.pdf` - Multi-document test 3

### Knowledge Base Files
- [ ] `knowledge/faq/` - FAQ documents directory
- [ ] `knowledge/policies.txt` - Company policies
- [ ] `knowledge/products/` - Product documentation
- [ ] `test-docs/new-policy.txt` - Runtime knowledge test

## 3. API Keys & Credentials

All stored in encrypted `secrets.enc`:

### LLM Providers
- [ ] `OPENAI_API_KEY` - OpenAI models + Whisper
- [ ] `GOOGLE_API_KEY` - Gemini models
- [ ] `ANTHROPIC_API_KEY` - Claude models (optional)

### Infrastructure
- [ ] `FAISSX_TENANT_ID` - FAISSx tenant identifier
- [ ] FAISSx auth credentials (for port 65432)
- [ ] Weather API keys
- [ ] Stock API keys
- [ ] Gmail OAuth tokens
- [ ] Database credentials

## 4. Python Dependencies

### Core Testing
```bash
pip install pytest pytest-asyncio anyio
```

### File Generation
```bash
pip install matplotlib seaborn plotly openpyxl python-docx python-pptx pandas
```

### Multimodal
```bash
# System dependency
sudo apt-get install ffmpeg  # or brew install ffmpeg

# Python packages
pip install Pillow PyPDF2
```

### Infrastructure
```bash
pip install psycopg2-binary asyncpg aiosqlite pyzmq cryptography
```

### All-in-one
```bash
pip install -e ".[file-generation,test,multimodal]"
```

## 5. Test Formations

Verify these exist in `test-formations/`:
- [ ] `formation-basic/` - Single agent setup
- [ ] `formation-memory/` - Memory configurations
- [ ] `formation-multi-agent/` - Agent routing tests
- [ ] `formation-file-generation/` - MCP testing
- [ ] `formation-complete/` - Full integration

## 6. Environment Setup

```bash
# Set environment variables
export MUXI_LOG_LEVEL=DEBUG
export MUXI_MASTER_KEY=your_master_key_here

# Verify Python version
python --version  # Should be 3.9+

# Check ffmpeg installation
ffmpeg -version
```

## 7. Directory Structure

Create if missing:
```bash
mkdir -p test-files
mkdir -p knowledge/faq
mkdir -p knowledge/products
mkdir -p test-docs
mkdir -p outputs
```

## 8. Service Startup Order

1. Start databases (PostgreSQL)
2. Start FAISSx servers
3. Start A2A Registry
4. Start webhook server
5. Start any external MCP servers
6. Run tests

## 9. Validation Commands

```bash
# Test PostgreSQL connection
psql -d muxi_test -c "SELECT 1"

# Test FAISSx servers
curl http://localhost:45678/health
curl http://localhost:65432/health

# Verify formations
python -m muxi.runtime.formation.validate test-formations/formation-basic/

# Test file generation dependencies
python -c "import matplotlib, seaborn, plotly, openpyxl, docx, pptx"
```

## 10. Important Notes

### File Size Limits
- OpenAI Whisper: 25MB maximum
- Video processing: 2GB soft limit
- Timeout: 300s for large files

### Content Types (Critical!)
- `.mov` → `video/quicktime`
- `.m4a` → `audio/m4a`
- `.mp3` → `audio/mp3`
- `.mp4` → `video/mp4`
- `.pdf` → `application/pdf`

### No Mock Services
- Use real LLM providers
- Use real API endpoints
- Use actual database instances
- No mocked responses

### Performance Targets
- Simple queries: < 2s
- Complex operations: < 30s
- Memory growth: < 100MB per 100 interactions

---

**Ready to Test?** Run through this checklist and ensure all items are prepared before starting the 12-day test plan!
