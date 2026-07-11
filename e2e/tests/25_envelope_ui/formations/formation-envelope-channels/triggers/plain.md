---
# Text-only formation-local transformer: the zero-change pin. A
# ui-bearing response delivered through this template must produce a
# payload with exactly the template's keys -- widgets never leak into
# templates that do not reference them.
transformer: plain
webhook: http://127.0.0.1:18254/plain-bridge
parse:
  message: $.payload.text
  user_id: $.payload.sender
  context:
    room: $.payload.room
---
${{ data.payload.text }}
