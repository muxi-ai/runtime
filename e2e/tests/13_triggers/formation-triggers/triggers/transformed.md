---
transformer: test-sink
parse:
  message: $.event.text
  user_id: $.event.user
  context:
    channel: $.event.channel
    thread_ts: $.event.thread_ts
---
Respond in one short sentence to this message: ${{ data.event.text }}
