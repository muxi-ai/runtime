---
# Inbound Slack message events; the bundled slack transformer formats
# the outbound reply as a chat.postMessage-style payload delivered to
# the test's local bridge sink.
transformer: slack
webhook: http://127.0.0.1:18254/slack-bridge
parse:
  message: $.event.text
  user_id: $.event.user
  context:
    channel: $.event.channel
    thread_ts: $.event.thread_ts
---
${{ data.event.text }}
