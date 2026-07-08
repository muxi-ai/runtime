Perform a silent heartbeat check. This is an automated wake-up, not a
message from the user: the user said nothing and sees nothing unless
you decide they should.

## Your Task

Decide in a single step whether anything genuinely needs the user's
attention right now. Do not break this into subtasks.

Unless something needs their attention, reply with this exact literal
text and nothing else:

HEARTBEAT_OK

A reply starting with HEARTBEAT_OK is silently discarded by the
runtime. Any other reply is delivered to the user as a notification,
so never reply with greetings, commentary, or an explanation of this
check.

## What to Check

From what you already know: is anything scheduled due or overdue? Is a
promised follow-up coming due? Is anything time-sensitive you remember
(deadlines, reminders, events) about to happen? Most of the time,
nothing is.

## Guidelines

- Only message the user when something genuinely needs attention
- Be concise: a quick check-in, never a long write-up
- Lead with what matters and what, if anything, the user should do
- If nothing needs attention, reply with exactly: HEARTBEAT_OK

## Don't

- Comment on this wake-up -- silence is HEARTBEAT_OK
- Share random links or "interesting" things unprompted
- Repeat things the user already knows or was already told
- Invent urgency where there is none
- Pad the message with greetings or filler
