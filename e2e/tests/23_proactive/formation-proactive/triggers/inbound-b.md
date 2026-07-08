---
channel: chan-b
parse:
  message: $.event.text
  user_id: $.event.user
  context:
    room: $.event.room
---
Respond in one short sentence to this message: ${{ data.event.text }}
