# Channel Templates

How MUXI formations talk to Slack, Telegram, Discord, and email without
platform SDKs, MCPs, or new delivery paths.

A channel integration is two declarative pieces riding existing machinery:

- **Inbound**: a trigger (`POST /v1/triggers/{id}`) with `parse:` extraction
  and `channel:` tagging.
- **Outbound**: a transformer (payload template, auth, retry) delivered by
  the standard transformer stack.

The runtime bundles dormant transformer templates for `slack`, `telegram`,
`discord`, and `email`. They define payload formats only -- no URLs, no
credentials -- and are inert until a trigger or `proactive.channels` entry
references them by name. A formation-local `transformers/<name>.yaml`
shadows a bundled template of the same name (the same rule as built-in
skills).

## Composition: transformer + webhook

In trigger frontmatter, `transformer:` and `webhook:` compose:

| Frontmatter | Behavior |
|---|---|
| `webhook:` only | Raw standard MUXI payload delivered to the URL (unchanged) |
| `transformer:` only | Formatted payload delivered to the transformer's own `endpoint.url` (unchanged) |
| both | Formatted payload delivered to the trigger's webhook URL |

URL resolution order: trigger/channel-supplied URL first, the transformer's
`endpoint.url` second. A transformer with no URL from either source fails at
formation load time, not at delivery time.

`proactive.channels` declarations get the same override via a `url:` key,
which may be a literal http(s) URL or a `${{ secrets.* }}` template:

```yaml
proactive:
  channels:
    slack:
      transformer: slack                        # bundled template
      url: "${{ secrets.SLACK_BRIDGE_URL }}"    # channel supplies the URL
```

## The developer owns the bridge

MUXI posts the platform-shaped payload to a URL you provide. Getting it the
last mile (bot token auth, SMTP, etc.) is your bridge's job. Messages are
text-only in v1.

## Slack

1. Create a bridge endpoint that forwards JSON to Slack `chat.postMessage`
   with your bot token (or accept an incoming-webhook URL directly).
2. Point your Slack app's event subscription (message events) at
   `POST /v1/triggers/slack` on your formation.
3. Add `triggers/slack.md`:

```markdown
---
transformer: slack
webhook: https://bridge.example.com/slack
parse:
  message: $.event.text
  user_id: $.event.user
  context:
    channel: $.event.channel
    thread_ts: $.event.thread_ts
channel: slack
---
Respond to this Slack message: ${{ data.event.text }}
```

Payload delivered to your bridge (`thread_ts` is dropped when absent):

```json
{"channel": "C0ABC123", "thread_ts": "1234.5678", "text": "..."}
```

## Telegram

1. Create a bot via @BotFather and set its webhook to
   `POST /v1/triggers/telegram` (or proxy through your bridge).
2. Your bridge forwards the payload to
   `https://api.telegram.org/bot<token>/sendMessage`.
3. Add `triggers/telegram.md`:

```markdown
---
transformer: telegram
webhook: https://bridge.example.com/telegram
parse:
  message: $.message.text
  user_id: $.message.from.id
  context:
    chat_id: $.message.chat.id
channel: telegram
---
Respond to this Telegram message: ${{ data.message.text }}
```

Payload (markdown stripped, capped at 4096 chars):

```json
{"chat_id": "123456789", "text": "..."}
```

## Discord

1. Create a channel webhook (channel settings > Integrations) or run a bot
   bridge that posts inbound messages to `POST /v1/triggers/discord`.
2. The `webhook:` URL can be the Discord webhook URL itself -- the payload
   is already in Discord's `content` format.
3. Add `triggers/discord.md`:

```markdown
---
transformer: discord
webhook: https://discord.com/api/webhooks/<id>/<token>
parse:
  message: $.content
  user_id: $.author.id
  context:
    channel_id: $.channel_id
channel: discord
---
Respond to this Discord message: ${{ data.content }}
```

Payload (capped at Discord's 2000-char limit):

```json
{"content": "..."}
```

## Email

1. Run a bridge that accepts the constructed message object and sends it
   via SMTP/SES/Mailgun/etc.
2. Point your inbound-email webhook (e.g. SES/Mailgun inbound parse) at
   `POST /v1/triggers/email`.
3. Add `triggers/email.md`:

```markdown
---
transformer: email
webhook: https://bridge.example.com/email
parse:
  message: $.body_plain
  user_id: $.sender
  context:
    address: $.sender
    subject: $.subject
channel: email
---
Respond to this email: ${{ data.body_plain }}
```

Payload (`from`/`subject` are dropped when absent; the bridge applies its
own defaults):

```json
{
  "from": "Assistant <assistant@example.com>",
  "to": "user@example.com",
  "subject": "Re: ...",
  "body": "...",
  "headers": {"X-Muxi-Agent": "assistant", "X-Muxi-Timestamp": "..."}
}
```

## Customizing a template

Copy the bundled file into your formation and edit it -- the local file
wins:

```
src/muxi/runtime/formation/background/builtin/transformers/slack.yaml
  -> <formation>/transformers/slack.yaml
```

Bundled templates never define `endpoint.url`; if your copy adds one, the
trigger's `webhook:`/channel's `url:` still takes precedence when present.
