---
# Bundled channel template composition: the 'slack' transformer ships with
# the runtime (payload format only); this trigger supplies the destination.
transformer: slack
webhook: http://127.0.0.1:18241/slack-bridge
parse:
  message: $.event.text
  user_id: $.event.user
  context:
    channel: $.event.channel
    thread_ts: $.event.thread_ts
channel: slack
---
Respond in one short sentence to this Slack message: ${{ data.event.text }}
