import json

import requests
'''
机器人开启了「隐私模式」（默认开启）

在默认状态下，机器人 无法收到群里任何普通消息，只会收到指令（如 /start），
所以你 getUpdates 看到的就只有私聊。

✔ 解决方法：关闭隐私模式

打开 @BotFather

输入 /mybots

选择你的 Bot

点击 Bot Settings

点击 Group Privacy

选择 Turn off

➡ 关闭后机器人就能收到群消息（包括文字消息）
'''
# 你的 API Token 和目标 Chat ID
API_TOKEN = ''  # 替换为你的实际 API Token
CHAT_ID = ''  # 替换为目标用户或机器人 Chat ID

# MESSAGE = '你好，这是我通过 \nPython 发的消息！'
# url = f'https://api.telegram.org/bot{API_TOKEN}/sendMessage'
# payload = {
#     'chat_id': CHAT_ID,
#     'text': MESSAGE
# }
# response = requests.post(url, json=payload)
get_chat_id_url = f"https://api.telegram.org/bot{API_TOKEN}/getUpdates"
response = requests.get(get_chat_id_url)
print(json.dumps(response.json(), ensure_ascii=False, indent=4))
pass