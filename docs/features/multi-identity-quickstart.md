# Multi-Identity Quick Start

Get started with MUXI's multi-identity system in 5 minutes.

## TL;DR

```python
# Same user across multiple platforms? Just use different IDs!
await formation.chat("Hello", user_id="alice@email.com")
await formation.chat("Hi", user_id="U12345ABC")  # Slack ID
await formation.chat("Hey", user_id="alice_gh")  # GitHub

# Want to link them? Use associate_user_identifiers()
from muxi.utils.user_resolution import associate_user_identifiers

await associate_user_identifiers(
    identifiers=["alice@email.com", "U12345ABC", "alice_gh"],
    muxi_user_id=None,  # Create new user or specify existing
    formation_id=formation._overlord.formation_id,
    db_manager=formation._overlord.db_manager,
    kv_cache=formation._overlord.kv_cache
)

# Now all three IDs resolve to the same user!
```

## Common Use Cases

### 1. Single User (Default)

Just use any consistent ID:

```python
response = await formation.chat(
    message="What's the weather?",
    user_id="user123"  # Any string works
)
```

**How it works**: First call creates user, subsequent calls reuse it.

### 2. Email-Based Users

Use email addresses as identifiers:

```python
response = await formation.chat(
    message="Remember my favorite color is blue",
    user_id="alice@example.com"
)

# Later...
response = await formation.chat(
    message="What's my favorite color?",
    user_id="alice@example.com"
)
# "Your favorite color is blue"
```

### 3. Slack Integration

Use Slack user IDs directly:

```python
# Slack event handler
@app.event("message")
async def handle_message(event):
    response = await formation.chat(
        message=event["text"],
        user_id=event["user"]  # U12345ABC
    )
    await slack_client.chat_postMessage(
        channel=event["channel"],
        text=response.content
    )
```

### 4. Multi-Platform User

Link email, Slack, and GitHub to one user:

```python
from muxi.utils.user_resolution import associate_user_identifiers

# Link all identifiers
result = await associate_user_identifiers(
    identifiers=[
        "alice@email.com",
        {"identifier": "U12345ABC", "type": "slack"},
        ("alice_gh", "github")
    ],
    muxi_user_id=None,  # Creates new user
    formation_id=formation._overlord.formation_id,
    db_manager=formation._overlord.db_manager,
    kv_cache=formation._overlord.kv_cache
)

print(f"Created user: {result['muxi_user_id']}")
# All three identifiers now share memory, preferences, etc.
```

### 5. API Integration with Multiple Auth Methods

Support both API keys and OAuth:

```python
# User signs up with email
user_email = "alice@example.com"

# Generate API key
api_key = generate_api_key()

# Link email and API key
await associate_user_identifiers(
    identifiers=[user_email, (api_key, "api_key")],
    muxi_user_id=None,
    formation_id=formation_id,
    db_manager=db_manager,
    kv_cache=kv_cache
)

# Both work now:
await formation.chat("Query", user_id=user_email)
await formation.chat("Query", user_id=api_key)
# Same user, same memory!
```

## Configuration

### Single-User Mode (SQLite - Default)

No configuration needed! Just use it:

```yaml
# formation.yaml
memory:
  provider: sqlite
  database: "./data/muxi.db"
```

### Multi-User Mode (PostgreSQL)

Switch to PostgreSQL for true multi-tenant:

```yaml
# formation.yaml
memory:
  provider: postgres
  host: localhost
  port: 5432
  database: muxi_db
  user: muxi_user
  password: ${POSTGRES_PASSWORD}
```

## How User Resolution Works

```
You call: formation.chat("Hello", user_id="alice@email.com")
     ↓
System checks cache: "user_id:formation_abc:alice@email.com"
     ↓
Cache hit? → Use cached user ID (fast!)
Cache miss? → Query database:
     ↓
     SELECT users.id, users.public_id
     FROM user_identifiers
     JOIN users ON user_identifiers.user_id = users.id
     WHERE user_identifiers.identifier = 'alice@email.com'
     ↓
Found? → Cache result, use user
Not found? → Create new user, create identifier, cache, use
```

## Key Concepts

### Internal vs External IDs

- **Your ID** (`user_id` parameter): Whatever you want (email, Slack ID, etc.)
- **Internal ID** (database): Integer for fast lookups
- **MUXI ID** (public_id): usr_xxxx for API responses

You only deal with "Your ID" - the system handles the rest.

### Formation Isolation

Each formation has its own user namespace:

```
Formation A: alice@email.com → User 123
Formation B: alice@email.com → User 456  # Different user!
```

This is intentional - keeps formations isolated.

### Cache Strategy

- **Where**: KV cache (Redis, etc.)
- **Key**: `user_id:{formation_id}:{identifier}`
- **Value**: `{internal_id}:{muxi_id}`
- **TTL**: 1 hour
- **Auto-invalidation**: On identifier changes

## Common Patterns

### Pattern: Slack Bot

```python
@app.event("message")
async def handle_slack_message(event):
    # Automatic user resolution
    response = await formation.chat(
        message=event["text"],
        user_id=event["user"]  # Slack user ID
    )
    return response.content
```

### Pattern: REST API with Auth

```python
@app.post("/chat")
async def chat_endpoint(request: ChatRequest, user: User = Depends(get_current_user)):
    # Use authenticated user's ID
    response = await formation.chat(
        message=request.message,
        user_id=user.email  # Or user.id, whatever you use
    )
    return {"response": response.content}
```

### Pattern: Anonymous → Authenticated

```python
# Step 1: Anonymous user
session_id = str(uuid.uuid4())
await formation.chat("Hello", user_id=f"anon_{session_id}")

# Step 2: User signs up
user_email = "alice@email.com"

# Step 3: Link anonymous session to email
await associate_user_identifiers(
    identifiers=[f"anon_{session_id}", user_email],
    muxi_user_id=None,
    formation_id=formation_id,
    db_manager=db_manager,
    kv_cache=kv_cache
)

# Step 4: All previous anonymous memories now belong to authenticated user!
```

## Error Handling

### Identifier Already Linked

```python
try:
    await associate_user_identifiers(
        identifiers=["alice@email.com"],
        muxi_user_id="usr_bob",  # But alice@email.com → usr_alice!
        formation_id=formation_id,
        db_manager=db_manager,
        kv_cache=kv_cache
    )
except IntegrityError:
    print("This identifier belongs to a different user!")
```

### Invalid Input

```python
try:
    await formation.chat("Hello", user_id="")  # Empty string
except ValueError as e:
    print(f"Invalid user_id: {e}")
```

## Performance Tips

1. **Always provide KV cache** - 10x faster than database lookups
2. **Use consistent identifiers** - Better cache hit rate
3. **Link identifiers upfront** - Avoids multiple user records
4. **Monitor cache hit rate** - Check observability events

## Next Steps

- **Full Guide**: [Multi-Identity Feature Documentation](multi-identity.md)
- **Architecture**: [Multi-User Architecture](../multi-user-architecture.md)
- **Memory System**: [Memory Systems](../memory-systems.md)
- **User Credentials**: [User Credentials](../user-credentials.md)

## FAQ

**Q: Do I need PostgreSQL?**  
A: No! SQLite works fine for single-user or testing. Use PostgreSQL for multi-tenant production.

**Q: What if I call with different user_id values?**  
A: Each unique identifier creates a separate user (unless you link them with `associate_user_identifiers`).

**Q: Is user data shared across formations?**  
A: No. Each formation has isolated user namespaces.

**Q: Can I change a user's identifier?**  
A: Yes, use `associate_user_identifiers` to add new identifiers. Old ones remain valid.

**Q: What happens if KV cache is down?**  
A: System falls back to database queries. Slower but still works.

**Q: How do I delete a user?**  
A: Delete from `users` table. Cascade deletes all identifiers and user data.

**Q: Can one identifier belong to multiple users?**  
A: No. One identifier → One user (per formation). Attempting otherwise raises `IntegrityError`.
