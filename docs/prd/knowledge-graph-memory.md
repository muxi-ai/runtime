# MUXI PRD: Knowledge Graph Memory + Captain's Log

**Version:** 1.0  
**Date:** January 24, 2026  
**Status:** Draft

---

## Summary

Evolve MUXI's memory system from flat fact extraction to a knowledge graph with narrative summaries. The knowledge graph captures structured relationships between entities (people, companies, projects, preferences). The Captain's Log captures temporal narrative — what happened, what was decided, how things evolved.

---

## Current State

- Vector DB with FIFO retention stores conversation chunks
- Real-time extraction pulls flat facts ("lives in London", "prefers minimal design")
- Facts stored as key-value pairs, no relationships between them

**Limitations:**
- No connections: "Ran is CEO of Automaze" and "Automaze is launching MUXI" are isolated facts
- No hierarchy: Can't query "what companies is Ran involved with?"
- No temporal narrative: Know facts, but not the story of how we got here

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE GRAPH                          │
│                  (Structured, Queryable)                    │
│                                                             │
│  Entities:           Relationships:                         │
│  ├─ People           ├─ works_at                           │
│  ├─ Companies        ├─ founded                            │
│  ├─ Projects         ├─ building                           │
│  ├─ Locations        ├─ lives_in                           │
│  ├─ Preferences      ├─ prefers                            │
│  └─ Topics           └─ interested_in                      │
│                                                             │
│  Example:                                                   │
│  (Ran)──[ceo_of]──▶(Automaze)──[building]──▶(MUXI)        │
│    │                    │                      │            │
│    ├──[lives_in]──▶(London)              [type: infra]     │
│    └──[prefers]──▶(minimal_design)       [status: launch]  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ Periodic summarization
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    CAPTAIN'S LOG                            │
│                 (Narrative, Temporal)                       │
│                                                             │
│  ## January 24, 2026                                        │
│  - Finalized PRD for proactive notifications                │
│  - Decided against org-level task templates                 │
│  - Planning knowledge graph migration                       │
│                                                             │
│  ## January 23, 2026                                        │
│  - Analyzed Clawdbot architecture                           │
│  - Compared memory approaches                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ Source
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    VECTOR DB (FIFO)                         │
│                  (Raw, Ephemeral)                           │
│                                                             │
│  [conversation chunks + embeddings]                         │
│  → Semantic search for retrieval                            │
│  → Source for extraction jobs                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Three Layers, Three Purposes

| Layer | What | Answers | Retention |
|-------|------|---------|-----------|
| **Vector DB** | Raw conversation chunks | "Find similar discussions" | FIFO (bounded) |
| **Knowledge Graph** | Entities + relationships | "Who/what/how connected" | Permanent |
| **Captain's Log** | Narrative summaries | "What happened when" | Permanent |

---

## Knowledge Graph Design

### Entity Types

| Entity | Attributes | Example |
|--------|------------|---------|
| `Person` | name, role, relationship_to_user | `{name: "Sarah", role: "CTO", rel: "colleague"}` |
| `Company` | name, type, user_role | `{name: "Automaze", type: "services", role: "founder"}` |
| `Project` | name, status, type | `{name: "MUXI", status: "launching", type: "product"}` |
| `Location` | name, type | `{name: "London", type: "city"}` |
| `Preference` | category, value | `{cat: "communication", val: "brief"}` |
| `Topic` | name, sentiment | `{name: "AI agents", sentiment: "positive"}` |

### Relationship Types

| Relationship | From → To | Example |
|--------------|-----------|---------|
| `works_at` | Person → Company | Ran works_at Automaze |
| `founded` | Person → Company | Ran founded Automaze |
| `building` | Person/Company → Project | Automaze building MUXI |
| `lives_in` | Person → Location | Ran lives_in London |
| `prefers` | User → Preference | User prefers minimal_design |
| `knows` | Person → Person | User knows Sarah |
| `interested_in` | User → Topic | User interested_in AI_agents |
| `part_of` | Entity → Entity | MUXI part_of Automaze |

### Querying

```python
# "What projects is Ran working on?"
graph.query(
    start="Ran",
    relationship=["building", "works_at.building"],
    target_type="Project"
)
# → [MUXI, Automaze client projects...]

# "Who do I know at Automaze?"
graph.query(
    start="User",
    relationship="knows",
    filter={"works_at": "Automaze"}
)
# → [Sarah, John...]

# "What are my communication preferences?"
graph.query(
    start="User",
    relationship="prefers",
    filter={"category": "communication"}
)
# → [brief, no_emojis, direct...]
```

---

## Extraction Pipeline

### Real-Time (During Conversation)

```python
# On each message, extract obvious entities/relationships
async def extract_realtime(message, context):
    # Quick extraction for high-confidence facts
    entities = await llm.extract(
        prompt=f"Extract entities and relationships:\n{message}",
        schema=EntitySchema,
        confidence_threshold=0.9  # Only high confidence
    )
    graph.upsert(entities)
```

### Periodic (Background Job)

```python
# Daily/hourly batch processing
async def extract_periodic(user_id: str):
    # 1. Pull recent chunks from vector DB
    chunks = vector_db.query(user_id, since=last_run)
    
    # 2. Deep extraction with full context
    entities = await llm.extract(
        prompt=f"Extract all entities and relationships:\n{chunks}",
        schema=EntitySchema,
        existing_graph=graph.snapshot(user_id)  # For deduplication
    )
    
    # 3. Update graph
    graph.upsert(entities)
    
    # 4. Generate Captain's Log entry
    summary = await llm.summarize(
        prompt="Summarize key events, decisions, and context:\n{chunks}"
    )
    captains_log.append(user_id, today(), summary)
```

---

## Captain's Log

### What Gets Captured

- Decisions made ("decided to use Postgres over SQLite")
- Projects discussed and their status changes
- Notable context ("preparing for investor meeting next week")
- Action items and outcomes
- Relationship changes ("met Sarah, new CTO at partner company")

### Format

```markdown
## January 24, 2026

**Projects:**
- MUXI: Finalized notification channels PRD, targeting 4-week implementation

**Decisions:**
- Rejected org-level task templates (privacy concerns)
- Will use WorkOS for org context sync instead

**Context:**
- Planning knowledge graph migration for memory system
- Comparing architecture with Clawdbot

**Action Items:**
- [ ] Write Captain's Log PRD
- [x] Compare Clawdbot memory system
```

### Usage

**Context injection:** Recent entries prepended to system prompt
```
[Recent context from your Captain's Log]
- Yesterday: Analyzed Clawdbot, compared memory systems
- Today: Working on knowledge graph PRD
```

**Search:** "What did we decide about the database?"
```python
captains_log.search(user_id, query="database decision")
# → "Jan 20: Decided to use Postgres over SQLite for..."
```

---

## Storage Options

### Knowledge Graph

| Option | Pros | Cons |
|--------|------|------|
| **Neo4j** | Purpose-built, powerful queries | Operational overhead |
| **PostgreSQL + Apache AGE** | Single DB, SQL familiarity | Less mature |
| **SQLite + JSON** | Simple, embedded | Limited graph queries |
| **NetworkX + persistence** | Python native, flexible | Not production-grade |

**Recommendation:** Start with PostgreSQL + simple adjacency tables. Migrate to Neo4j/AGE if query complexity warrants.

### Captain's Log

Simple timestamped text entries. Can be:
- Column in user table (JSONB array)
- Separate table (user_id, date, summary)
- Markdown files (if we want Clawdbot-style transparency)

---

## Migration Path

### Phase 1: Schema + Extraction
- Define entity/relationship types
- Build extraction pipeline (real-time + periodic)
- Run alongside existing flat facts

### Phase 2: Graph Storage
- Implement graph storage layer
- Migrate existing facts to graph structure
- Build query interface

### Phase 3: Captain's Log
- Add periodic summarization job
- Store log entries
- Inject into agent context

### Phase 4: Deprecate Flat Facts
- Route all queries through graph
- Remove legacy fact storage
- Optimize extraction for graph schema

---

## Success Criteria

- Agent can answer relationship queries ("who do I work with?")
- Agent references temporal context naturally ("last week you decided...")
- No increase in memory latency (sub-100ms retrieval)
- Users feel understood without manual memory management

---

## Open Questions

1. **Graph depth:** How many hops to traverse for context injection?
2. **Entity resolution:** How to merge "Ran" vs "Ran Aroussi" vs "@ran"?
3. **Confidence decay:** Should old, unconfirmed facts fade?
4. **User editing:** Should users be able to edit the graph directly?

---

*End of Document*
