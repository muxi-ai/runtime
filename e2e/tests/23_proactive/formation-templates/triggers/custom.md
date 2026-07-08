---
# Formation-local URL-less transformer + trigger-supplied webhook URL:
# the same composition mechanism with a custom payload shape.
transformer: custom-format
webhook: http://127.0.0.1:18241/custom-bridge
parse:
  message: $.payload.text
  user_id: $.payload.sender
  context:
    room: $.payload.room
---
Respond in one short sentence to this message: ${{ data.payload.text }}
