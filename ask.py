import os
import base64

import requests
from string import Template

prompt_template = Template(base64.b64decode(os.getenv("prompt_template_short")).decode())

delimaters = (
  "####",
  "$$$$",
  "^^^^",
  "@@@@",
  "****"
)

CHAT_TOKEN = os.getenv("chat_token")


def prompt(text):
    delimater = "####"
    for d in delimaters:
        if d not in text:
            delimater = d
            break
    text = text.replace(delimater, " ")
    return prompt_template.substitute(delimater=delimater, content=text)


def openai(openid, text):
    resp = requests.post(
        url=os.getenv("chat_url"),
        json={
            "content": prompt(text),
            "model": "text-davinci-002-render-sha-mobile",
            "openid": openid,
            "new_chat": False
        },
        headers={
            "Authorization": f"Bearer {CHAT_TOKEN}",
            "Content-Type": "application/json"
        }
    )
    if resp.status_code == 200:
        return resp.text
    else:
        return "请稍后重试。"
