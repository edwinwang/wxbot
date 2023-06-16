import hashlib
import asyncio
from functools import partial
import time
import os

from werobot import WeRoBot
from fastapi import APIRouter, status
from fastapi.responses import PlainTextResponse
from starlette.requests import Request
from starlette.background import BackgroundTask
import redis

import ask

wxbot = WeRoBot(token=os.getenv("wx_token"))

wxbot.config["APP_ID"] = os.getenv("wx_appid")
wxbot.config["APP_SECRET"] = os.getenv("wx_appkey")
wxbot.config["ENCODING_AES_KEY"] = os.getenv("wx_encode_key")

MSG_LENGTH_LIMIT = 2000

redis = redis.Redis(os.getenv("redis_url"))

def ask_task(msgid, text):
    redis.hset(msgid, "question", text)
    resp = ask.openai(text)
    redis.hset(msgid, "answer", resp)
    return resp


def query_answer(msgid, loop=5):
    while loop >= 0:
        if redis.hget(msgid, "answer"):
            return redis.hget(msgid, "answer")
        time.sleep(1)
        loop -= 1
    return None

def decode_value(val):
    val= val.decode('utf-8')
    if val.isdigit():
        return int(val)
    return val


def query_user_info(openid: str):
    data = redis.hgetall(openid)
    return {key.decode('utf-8'): decode_value(value) for key, value in data.items()}

def update_user_info(openid: str, userinfo: dict):
    print(openid, userinfo)
    redis.hmset(openid, userinfo)
    redis.expire(openid, 86400)

def prepare_answer():
    pass

wait_text_2 = "正在准备回答, 请耐心等待"
wait_text = "正在思考，请耐心等待，稍后发送任意消息获取回复"
wait_last_text = "正在准备上一个回答，请耐心等待"
retry_text = "请求出错，请稍后重试"
text_too_long = "文本太长"


@wxbot.text
def echo(message):
    openid = message.source
    msgid = message.message_id
    userinfo = query_user_info(openid) or {}
    last_msgid = userinfo.get("last_msgid")
    print(">>>>>>>>>>>>", msgid)
    if redis.lock("lock:" + openid).locked(): #正在生成回答
        print("11111111111")
        if msgid != last_msgid:
            return wait_last_text
        else:
            userinfo["retry"] += 1
            update_user_info(openid, userinfo)
            retry = userinfo["retry"]
            if retry < 3:
                print("2222222222222")
                resp = query_answer(msgid)
                print("33333333333333")
            else:
                print(444444444444)
                resp = query_answer(last_msgid, loop=2)
                print(55555555555555)
            if resp:
                userinfo["last_ok"] = 1
                update_user_info(openid, userinfo)
            else:
                resp = wait_text
            return resp

    with redis.lock("lock:" + openid):
        userinfo = query_user_info(openid) or {}
        last_ok = userinfo.get("last_ok", 1)
        print(msgid, last_ok, userinfo.get("last_msgid"))
        if userinfo.get("last_msgid") == msgid:
            if last_ok:
                return query_answer(msgid)
            retry = userinfo['retry'] + 1
            resp = query_answer(msgid, loop=2 if retry == 3 else None)
            if resp:
                userinfo['last_ok'] = 1
                update_user_info(openid, userinfo)
                return resp
            if retry == 3:
                return wait_text
            else:
                userinfo['retry'] = retry
                update_user_info(openid, userinfo)
                return wait_text
        else:
            if not last_ok:
                last_msgid = userinfo.get("last_msgid", 0)
                if last_msgid:
                    resp = query_answer(userinfo.get("last_msgid"), loop=1)
                    if resp:
                        userinfo['last_ok'] = 1
                        update_user_info(openid, userinfo)
                        return resp
                    else:
                        return wait_text
            msg = message.content
            print(msg)
            if len(msg) > MSG_LENGTH_LIMIT:
                return text_too_long
            userinfo['last_msgid'] = msgid
            userinfo['last_ok'] = 0
            userinfo['retry'] = 1
            userinfo['working'] = 1
            update_user_info(openid, userinfo)
            resp = ask_task(msgid, message.content)
            print(resp)
            if resp:
                userinfo = query_user_info(openid)
                if userinfo['last_msgid'] == msgid and userinfo["retry"]==1:
                    userinfo['last_ok'] = 1
                    update_user_info(openid, userinfo)
                return resp
            return wait_text


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
def wechat_check(signature: str=None, timestamp: str=None, nonce: str=None, echostr: str=None):
    '''
    微信接口检测
    '''
    if not signature or not timestamp or not nonce or not echostr:
        return PlainTextResponse('', status_code=429)
    token = "9XjY2KmzF1LcNqo6v0Gt"
    check_list = [token, timestamp, nonce]
    check_list.sort()
    str1 = ''.join(check_list)
    sha1 = hashlib.sha1(str1.encode())
    res = sha1.hexdigest()
    if res == signature:
        return PlainTextResponse(echostr)
    else:
        return PlainTextResponse("")


@router.post("/")
async def hanler(request: Request):
    body = (await request.body()).decode("utf-8")
    query_params = request.query_params
    func = partial(
        wxbot.parse_message,
        body=body,
        timestamp=query_params.get("timestamp"),
        nonce=query_params.get("nonce"),
        msg_signature=query_params.get("msg_signature")

    )
    try:
        message = wxbot.parse_message(
            body=body,
            timestamp=query_params.get("timestamp"),
            nonce=query_params.get("nonce"),
            msg_signature=query_params.get("msg_signature")
        )
        func = partial(
            wxbot.get_encrypted_reply,
            message
        )
        resp = await asyncio.wait_for(asyncio.to_thread(func), timeout=5)
        return PlainTextResponse(resp, status_code=200)
    except asyncio.TimeoutError:
        print("Timeout!")
        return PlainTextResponse(retry_text)
