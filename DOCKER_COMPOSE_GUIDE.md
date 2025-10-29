# Docker Compose Usage Guide

**Complete guide for running MUXI Runtime with Docker Compose**

---

## 🚀 Quick Start (5 Minutes)

### 1. Setup Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your API keys
nano .env  # or your favorite editor
```

**Minimum required**: Add your `OPENAI_API_KEY` (or another LLM provider)

### 2. Create Formations Directory

```bash
# Create directory for your formations
mkdir -p formations

# Add a test formation
cat > formations/test.yaml << 'EOF'
schema: "1.0.0"
id: test-formation
description: "Test formation"

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"

agents:
  - id: assistant
    name: "Test Assistant"
    description: "A helpful assistant"
    system_message: "You are a helpful AI assistant."
EOF
```

### 3. Run MUXI

```bash
# Start MUXI Runtime
docker-compose up muxi

# Or run in background
docker-compose up -d muxi
```

### 4. Test It

```bash
# Check health
curl http://localhost:8000/health

# Run a formation (if server mode is enabled)
# Access: http://localhost:8000
```

---

## 📋 Available Services

### Main Service: `muxi`

**Default service** - Optimized 2.4GB image with all features.

```bash
# Start
docker-compose up muxi

# Stop
docker-compose down

# Restart
docker-compose restart muxi

# View logs
docker-compose logs -f muxi
```

**What's Included:**
- Full Python ML stack
- All LLM providers support
- Document processing
- Vector search (FAISS)
- All runtime features

**Access:** http://localhost:8000

---

### Production Service: `muxi-production`

**Full stack** with PostgreSQL and pgvector for production deployments.

```bash
# Start production setup (includes PostgreSQL)
docker-compose up muxi-production postgres

# Or in background
docker-compose up -d muxi-production postgres
```

**What's Included:**
- Everything in `muxi`
- PostgreSQL with pgvector
- Persistent storage
- Production optimizations

**Access:** http://localhost:8001

---

## ⚙️ Configuration

### Environment Variables (.env file)

**Required:**
```bash
# At least one LLM API key
OPENAI_API_KEY=sk-your-key-here
```

**Optional:**
```bash
# Other LLM providers
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
COHERE_API_KEY=...

# Ports
MUXI_PORT=8000              # Main service port
MUXI_PROD_PORT=8001         # Production service port

# Directories
FORMATIONS_DIR=./formations  # Where your YAML files are
DATA_DIR=./data             # Persistent data
LOGS_DIR=./logs             # Log files

# PostgreSQL (for production)
POSTGRES_DB=muxi
POSTGRES_USER=muxi
POSTGRES_PASSWORD=change_me_in_production
```

---

## 📁 Directory Structure

```
runtime/
├── docker-compose.yaml     # Compose configuration
├── .env                    # Your environment (gitignored)
├── .env.example           # Template
├── formations/            # Your formation YAMLs
│   ├── my-agent.yaml
│   └── secrets.env        # Formation secrets (optional)
├── data/                  # Persistent data (auto-created)
└── logs/                  # Application logs (auto-created)
```

---

## 📖 Common Usage Patterns

### Pattern 1: Simple Development

**Use Case:** Testing formations locally

```bash
# 1. Setup
cp .env.example .env
# Add OPENAI_API_KEY to .env

# 2. Create formation
mkdir formations
echo "your formation YAML" > formations/test.yaml

# 3. Run
docker-compose up muxi

# 4. Access
curl http://localhost:8000/health
```

**Best For:**
- Local development
- Formation testing
- Quick experiments

---

### Pattern 2: Production Deployment

**Use Case:** Running in production with persistent storage

```bash
# 1. Setup environment
cp .env.example .env
# Configure all needed API keys
# Set strong POSTGRES_PASSWORD

# 2. Start services
docker-compose up -d muxi-production postgres

# 3. Verify
docker-compose ps
docker-compose logs muxi-production

# 4. Access
curl http://localhost:8001/health
```

**Best For:**
- Production deployments
- Multi-user setups
- Long-term storage needs

---

### Pattern 3: Multi-Formation Testing

**Use Case:** Running multiple formations

```bash
# Directory structure
formations/
├── agent-1/
│   ├── formation.yaml
│   └── secrets.env
├── agent-2/
│   ├── formation.yaml
│   └── secrets.env
└── shared/
    └── common-config.yaml

# Mount all formations
# (Already configured in docker-compose.yaml)
docker-compose up muxi
```

---

## 🔧 Advanced Usage

### Custom Port

```bash
# Method 1: .env file
echo "MUXI_PORT=9000" >> .env
docker-compose up muxi

# Method 2: Override
MUXI_PORT=9000 docker-compose up muxi

# Method 3: docker-compose override
# Create docker-compose.override.yaml
```

---

### Mount Specific Formation

```bash
# Edit docker-compose.yaml or create override
services:
  muxi:
    volumes:
      - ./my-special-formation:/formations/special:ro
```

---

### Resource Limits

Uncomment in `docker-compose.yaml`:

```yaml
services:
  muxi:
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
```

---

### Database Backups (Production)

```bash
# Backup
docker-compose exec postgres pg_dump -U muxi muxi > backup.sql

# Restore
docker-compose exec -T postgres psql -U muxi muxi < backup.sql

# Or use volume backup
docker run --rm -v muxi-postgres-data:/data -v $(pwd):/backup \
  busybox tar czf /backup/postgres-backup.tar.gz /data
```

---

## 🐛 Troubleshooting

### Issue: Container Won't Start

**Check logs:**
```bash
docker-compose logs muxi
```

**Common causes:**
- Missing API key in .env
- Port already in use
- Insufficient resources

**Fix:**
```bash
# Check if port is in use
lsof -i :8000

# Stop other services using port
docker-compose down

# Rebuild if needed
docker-compose up --build muxi
```

---

### Issue: Can't Connect to PostgreSQL

**Check postgres is running:**
```bash
docker-compose ps postgres
docker-compose logs postgres
```

**Test connection:**
```bash
docker-compose exec postgres psql -U muxi -d muxi -c "SELECT version();"
```

**Reset database:**
```bash
docker-compose down
docker volume rm muxi-postgres-data
docker-compose up postgres
```

---

### Issue: Formation Not Found

**Check mounts:**
```bash
# List files in container
docker-compose exec muxi ls -la /formations

# Check your local directory
ls -la ./formations
```

**Fix:**
```bash
# Ensure formations directory exists
mkdir -p formations

# Restart with fresh mount
docker-compose down
docker-compose up muxi
```

---

### Issue: High Memory Usage

**Monitor resources:**
```bash
docker stats muxi-runtime
```

**Add limits:**
Edit `docker-compose.yaml` and uncomment resource limits.

**Restart:**
```bash
docker-compose restart muxi
```

---

## 📊 Monitoring

### View Logs

```bash
# All logs
docker-compose logs

# Specific service
docker-compose logs muxi

# Follow logs (live)
docker-compose logs -f muxi

# Last 100 lines
docker-compose logs --tail=100 muxi

# Since timestamp
docker-compose logs --since 2024-10-29T10:00:00 muxi
```

---

### Health Checks

```bash
# Check container health
docker-compose ps

# Manual health check
curl http://localhost:8000/health

# Detailed status
docker inspect muxi-runtime | grep -A 10 Health
```

---

### Resource Usage

```bash
# Real-time stats
docker stats muxi-runtime

# Container info
docker-compose top muxi
```

---

## 🔄 Maintenance

### Update Image

```bash
# Rebuild from latest code
docker-compose build muxi

# Or pull if using registry
docker-compose pull muxi

# Restart with new image
docker-compose up -d muxi
```

---

### Clean Up

```bash
# Stop and remove containers
docker-compose down

# Also remove volumes (CAUTION: deletes data!)
docker-compose down -v

# Remove old images
docker image prune -a

# Complete cleanup
docker system prune -a --volumes
```

---

### Backup Data

```bash
# Backup data directory
tar czf muxi-data-backup.tar.gz data/

# Backup formations
tar czf muxi-formations-backup.tar.gz formations/

# Backup everything
tar czf muxi-complete-backup.tar.gz data/ formations/ .env
```

---

## 🚀 Production Checklist

Before deploying to production:

- [ ] Change default PostgreSQL password in `.env`
- [ ] Set resource limits in `docker-compose.yaml`
- [ ] Enable restart policies (`restart: always`)
- [ ] Set up log rotation
- [ ] Configure backup strategy
- [ ] Test failover scenarios
- [ ] Monitor with external tools (Prometheus, etc.)
- [ ] Use secrets management (Docker secrets, Vault)
- [ ] Enable HTTPS/TLS
- [ ] Set up firewall rules
- [ ] Configure log aggregation
- [ ] Test disaster recovery

---

## 📚 Additional Resources

- **Docker Docs**: `DOCKER_FINAL.md` - Configuration details
- **Size Analysis**: `DOCKER_SIZE_ANALYSIS.md` - Image optimization
- **Test Results**: `DOCKER_TEST_SUMMARY.md` - Test reports
- **Build Guide**: `DOCKER-GUIDE.md` - Building images

---

## 💡 Tips & Best Practices

### Development
- Use `.env` file for secrets (never commit it!)
- Mount formations as read-only (`:ro`)
- Use named volumes for persistence
- Enable health checks
- View logs regularly

### Production
- Use strong passwords
- Set resource limits
- Enable automatic restarts
- Back up data regularly
- Monitor container health
- Use external secrets management
- Enable SSL/TLS
- Use reverse proxy (nginx, traefik)

### Performance
- Give containers adequate resources
- Use volumes for I/O intensive operations
- Monitor memory usage
- Enable connection pooling
- Use caching where possible

---

## 🆘 Getting Help

**Check logs first:**
```bash
docker-compose logs -f muxi
```

**Common issues:**
1. Missing API keys → Check `.env` file
2. Port conflicts → Change `MUXI_PORT`
3. Resource limits → Increase Docker resources
4. Permission errors → Check volume mounts

**Still stuck?**
- GitHub Issues: https://github.com/muxi-ai/runtime/issues
- Documentation: https://muxi.org/docs
- Discussions: https://github.com/muxi-ai/runtime/discussions

---

**Happy MUXI Running! 🚀**
