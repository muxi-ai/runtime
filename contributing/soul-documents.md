# Soul Documents

A soul document gives an agent values, philosophy, and relationship
dynamics beyond functional persona instructions. The persona answers
"what does this agent do?"; the soul answers "who is this agent?".

| Aspect | Persona / system message | Soul |
|---|---|---|
| Focus | Capabilities, role, instructions | Values, philosophy, relationship |
| Typical content | "Help users with X, Y, Z" | "I value honesty over politeness" |
| Required | Yes | No (optional enhancement) |

## Wiring it up

```yaml
agents:
  - id: my-assistant
    soul: ./SOUL.md
```

Rules (enforced at formation load time):

- The path must be **relative** and resolve **inside the formation
  directory** (same confinement as knowledge paths).
- The file must **exist** -- a missing soul document is a load error,
  not a silent skip.
- The content is prepended **verbatim** to the agent's system message.
  There is no templating; what you write is what the model sees.

This agent-level `soul:` is distinct from the overlord-level soul
(`SOUL.md` in the formation root / `overlord.soul`), which feeds the
overlord's default persona. An agent soul shapes one agent.

## Starter template

Copy [templates/soul.md](templates/soul.md) into your formation as
`SOUL.md` and edit. It carries the five recommended sections with
guidance comments (delete the comments once filled in -- they would be
sent to the model too):

- **Who I Am** -- identity in one or two sentences
- **My Values** -- trade-offs in "X over Y" form, so the model knows
  which side to pick when principles collide
- **My Boundaries** -- behavioral commitments held even when pushed
- **Our Relationship** -- the working dynamic: peer, advisor, executor
- **What I Remember** -- how the agent should think about continuity

## Writing guidance

- **First person.** "I'll push back if you're making a mistake" lands
  harder than "the assistant should challenge the user".
- **Trade-offs, not virtues.** "Honesty over sycophancy" instructs;
  "be honest" decorates.
- **Short.** The soul rides on every request of that agent. A page is
  plenty; a paragraph per section is better.
- **No capabilities.** Tool lists, output formats, and task procedures
  belong in the persona/system message or SOPs, not the soul.
