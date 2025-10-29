# Docker Compose - Quick Start

**Get MUXI running with Docker Compose in 5 minutes!**

---

## 🚀 Quick Start

### 1. Copy Environment Template
```bash
cp .env.example .env
```

### 2. Add Your API Key
Edit `.env` and add your OpenAI key (or any other LLM provider):
```bash
OPENAI_API_KEY=sk-your-actual-key-here
```

### 3. Start MUXI
```bash
# Using Docker Compose v2 (recommended)
docker compose up muxi

# Or with older docker-compose
docker-compose up muxi

# Run in background
docker compose up -d muxi
```

### 4. Verify It's Running
```bash
# Check status
docker compose ps

# Check health
curl http://localhost:8000/health

# View logs
docker compose logs -f muxi
```

---

## 📁 Directory Structure

The following directories are automatically created:

```
runtime/
├── formations/        # Put your formation YAMLs here
├── data/             # Persistent data (auto-created)
└── logs/             # Application logs (auto-created)
```

---

## 📝 Example Formation

Create a test formation:

```bash
cat > formations/my-agent.yaml << 'EOF'
schema: "1.0.0"
id: my-test-agent
description: "My first agent"

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"

agents:
  - id: assistant
    name: "My Assistant"
    description: "A helpful AI assistant"
    system_message: "You are a helpful assistant."
EOF
```

---

## 🎯 Common Commands

```bash
# Start
docker compose up muxi

# Start in background
docker compose up -d muxi

# Stop
docker compose down

# Stop and remove volumes (⚠️ deletes data!)
docker compose down -v

# Restart
docker compose restart muxi

# View logs
docker compose logs -f muxi

# Check status
docker compose ps

# Rebuild image (after code changes)
docker compose build muxi
docker compose up muxi
```

---

## 🔧 Configuration

### Default Values (from .env)

| Variable | Default | Description |
|----------|---------|-------------|
| `MUXI_PORT` | 8000 | Main service port |
| `FORMATIONS_DIR` | ./formations | Where formations are |
| `DATA_DIR` | ./data | Persistent data |
| `LOGS_DIR` | ./logs | Log files |

### Override Defaults

**Method 1: Edit .env file**
```bash
echo "MUXI_PORT=9000" >> .env
```

**Method 2: Environment variable**
```bash
MUXI_PORT=9000 docker compose up muxi
```

**Method 3: Create docker-compose.override.yaml**
```yaml
services:
  muxi:
    ports:
      - "9000:8000"
```

---

## 🏗️ Production Setup

For production with PostgreSQL:

```bash
# 1. Configure database password in .env
echo "POSTGRES_PASSWORD=your-secure-password" >> .env

# 2. Start both services
docker compose up -d muxi-production postgres

# 3. Check status
docker compose ps
```

Access production service at: http://localhost:8001

---

## 🐛 Troubleshooting

### Port Already in Use

```bash
# Change port in .env
echo "MUXI_PORT=9000" >> .env
docker compose up muxi
```

### Can't Connect

```bash
# Check if container is running
docker compose ps

# Check logs
docker compose logs muxi

# Check health
curl http://localhost:8000/health
```

### Missing API Key

```bash
# Verify .env file exists and has your key
cat .env | grep OPENAI_API_KEY

# Restart after adding key
docker compose restart muxi
```

### Formation Not Found

```bash
# Check formations are mounted
docker compose exec muxi ls -la /formations

# Verify local directory
ls -la formations/
```

---

## 📖 Full Documentation

For complete guide, see: **[DOCKER_COMPOSE_GUIDE.md](./DOCKER_COMPOSE_GUIDE.md)**

---

## 🆘 Need Help?

```bash
# View logs
docker compose logs -f muxi

# Check configuration
docker compose config

# Verify image exists
docker images | grep muxi-runtime
```

**Still stuck?**
- Check logs first
- Verify API key in .env
- Ensure port 8000 is available
- See full guide: DOCKER_COMPOSE_GUIDE.md

---

**Happy MUXI Running! 🚀**
