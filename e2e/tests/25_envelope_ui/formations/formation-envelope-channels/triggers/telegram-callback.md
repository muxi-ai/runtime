---
# Inbound Telegram callback_query updates (inline keyboard button
# presses). parse.ui_response decodes the button's callback data into
# the {id, index} reply hint that pins the selection deterministically.
transformer: telegram
webhook: http://127.0.0.1:18254/telegram-bridge
parse:
  user_id: $.callback_query.from.id
  ui_response: $.callback_query.data
  context:
    chat_id: $.callback_query.message.chat.id
---
The user pressed an inline keyboard button (callback: ${{ data.callback_query.data }}).
