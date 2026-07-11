---
# Inbound Telegram message updates (bridge forwards Bot API webhooks).
# The bundled telegram transformer formats the outbound reply; the
# webhook URL is the test's local bridge sink.
transformer: telegram
webhook: http://127.0.0.1:18254/telegram-bridge
parse:
  message: $.message.text
  user_id: $.message.from.id
  context:
    chat_id: $.message.chat.id
---
${{ data.message.text }}
