# Soul Documents

A soul document gives the overlord values, philosophy, and relationship
dynamics beyond functional persona instructions. The persona answers
"what does this assistant do?"; the soul answers "who is this
assistant?".

| Aspect | Persona / system message | Soul |
|---|---|---|
| Focus | Capabilities, role, instructions | Values, philosophy, relationship |
| Typical content | "Help users with X, Y, Z" | "I value honesty over politeness" |
| Required | Yes | No (optional enhancement) |

Soul is an **overlord-only** concept -- it shapes the formation's
default persona, the voice users talk to. Individual agents are
single-file contained: an agent's character lives entirely in its
`system_message`.

## Wiring it up

Place a `SOUL.md` (or `soul.md`) file next to `formation.yaml`. It is
auto-discovered at formation load time -- no config key needed.

Precedence: `SOUL.md` > `soul.md` > inline `overlord.soul` > built-in
default.

- The content is used **verbatim** as the overlord's default persona.
  There is no templating; what you write is what the model sees.
- The inline `overlord.soul` config key still works, but a soul file
  next to the formation always wins.

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
- **What I Remember** -- how the assistant should think about continuity

## Writing guidance

- **First person.** "I'll push back if you're making a mistake" lands
  harder than "the assistant should challenge the user".
- **Trade-offs, not virtues.** "Honesty over sycophancy" instructs;
  "be honest" decorates.
- **Short.** The soul rides on every request the overlord handles. A
  page is plenty; a paragraph per section is better.
- **No capabilities.** Tool lists, output formats, and task procedures
  belong in the persona/system message or SOPs, not the soul.
