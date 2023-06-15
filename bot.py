import hashlib
import asyncio
from functools import partial
import time
import os

from werobot import WeRoBot
from fastapi import APIRouter
from starlette.requests import Request
from starlette.background import BackgroundTask
import redis

import ask

wxbot = WeRoBot(token=os.getenv("wx_token"))

wxbot.config["APP_ID"] = os.getenv("wx_appid")
wxbot.config["APP_SECRET"] = os.getenv("wx_appkey")
wxbot.config["ENCODING_AES_KEY"] = os.getenv("wx_encode_key")

MSG_LENGTH_LIMIT = 2000

redis = redis.Redis(url=os.getenv("redis_url"))

def ask_task(msgid, text):
    redis.hset(msgid, "question", text)
    resp = ask.openai(msgid, text)
    redis.hset(msgid, "answer", resp)


def query_answer(msgid, loop=5):
    while loop >= 0:
        if redis.hget(msgid, "answer"):
            return redis.hget(msgid, "answer")
        time.sleep(1)
    return None


@wxbot.text
def echo(message, session, background_tasks: BackgroundTask):
    msgid = message.message_id
    last_ok = session.get("last_ok", 0)
    if session.get("last_msgid") == msgid:
        if last_ok:
            return ''
        retry = session['retry'] + 1
        resp = query_answer(msgid, loop=3 if retry == 3 else None)
        if resp:
            session['last_ok'] = 1
            return resp
        if retry == 3:
            return "正在思考，请耐心等待，稍后发送任意消息获取回复"
    else:
        if not last_ok:
            last_msgid = session.get("last_msgid", 0)
            if last_msgid:
                resp = query_answer(session.get("last_msgid"), loop=1)
                if resp:
                    session['last_ok'] = 1
                    return resp
                else:
                    return "正在准备，稍后发送任意消息获取回复"
        else:
            msg = message.content
            if len(msg) > MSG_LENGTH_LIMIT:
                return "文本太长"
            session['last_msgid'] = msgid
            session['last_ok'] = 0
            session['retry'] = 1
            background_tasks.add_task(ask_task, msgid, message.content)
            resp = query_answer(msgid)
            if resp:
                session['last_ok'] = 1
                return resp
            return "正在思考，请耐心等待，稍后发送任意消息获取回复"


@wxbot.image
def image(message):
    return message.img


@wxbot.voice
def voice(message):
    return message.recognition


def create_menu():
    client = wxbot.client
    client.create_menu({
        "button": [{
            "type": "click",
            "name": "今日歌曲",
            "key": "music"
        }]
    })


@wxbot.key_click("music")
def music(message):
    '''响应菜单'''
    return '你点击了“今日歌曲”按钮'


router = APIRouter()


@router.get("/")
def wechat_check(signature: str, timestamp: str, nonce: str, echostr: str):
    '''
    微信接口检测
    '''

    if not signature or not timestamp or not nonce or not echostr:
        return ""
    token = "9XjY2KmzF1LcNqo6v0Gt"
    check_list = [token, timestamp, nonce]
    check_list.sort()
    str1 = ''.join(check_list)
    sha1 = hashlib.sha1(str1.encode())
    res = sha1.hexdigest()
    if res == signature:
        return echostr
    else:
        return ""


@router.post("/")
async def hanler(request: Request):
    body = await request.body().decode("utf-8")
    query_params = request.query_params
    loop = asyncio.get_running_loop()
    func = partial(
        wxbot.parse_message,
        body=body,
        timestamp=query_params.timestamp,
        nonce=query_params.nonce,
        msg_signature=query_params.msg_signature

    )
    message = await loop.run_in_executor(None, func)
    return wxbot.get_encrypted_reply(message)
