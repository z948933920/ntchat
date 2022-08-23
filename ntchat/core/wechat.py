import pyee
import json
from ntchat.core.mgr import WeChatMgr
from ntchat.const import wx_type
from threading import Event
from ntchat.wc import wcprobe
from ntchat.utils import generate_guid
from ntchat.utils import logger
from ntchat.exception import WeChatNotLoginError
from functools import wraps
from typing import (
    List,
    Union,
    Tuple
)

log = logger.get_logger("WeChatInstance")


class ReqData:
    __response_message = None
    msg_type: int = 0
    request_data = None

    def __init__(self, msg_type, data):
        self.msg_type = msg_type
        self.request_data = data
        self.__wait_event = Event()

    def wait_response(self, timeout=None):
        self.__wait_event.wait(timeout)
        return self.get_response_data()

    def on_response(self, message):
        self.__response_message = message
        self.__wait_event.set()

    def get_response_data(self):
        if self.__response_message is None:
            return None
        return self.__response_message["data"]


class WeChat:
    client_id: int = 0
    pid: int = 0
    status: bool = False
    login_status: bool = False

    def __init__(self):
        WeChatMgr().append_instance(self)
        self.__wait_login_event = Event()
        self.__req_data_cache = {}
        self.__msg_event_emitter = pyee.EventEmitter()
        self.__login_info = {}

    def on(self, msg_type, f):
        return self.__msg_event_emitter.on(str(msg_type), f)

    def msg_register(self, msg_type: Union[int, List[int], Tuple[int]]):
        if not (isinstance(msg_type, list) or isinstance(msg_type, tuple)):
            msg_type = [msg_type]

        def wrapper(f):
            wraps(f)
            for event in msg_type:
                self.on(event, f)
            return f
        return wrapper

    def on_recv(self, message):
        msg_type = message["type"]
        extend = message.get("extend", None)
        if msg_type == wx_type.MT_USER_LOGIN_MSG:
            self.login_status = False
            self.__wait_login_event.set()
            self.__login_info = message.get("data", {})
        elif msg_type == wx_type.MT_USER_LOGOUT_MSG:
            self.login_status = False

        if extend is not None and extend in self.__req_data_cache:
            req_data = self.__req_data_cache[extend]
            req_data.on_response(message)
            del self.__req_data_cache[extend]
        else:
            self.__msg_event_emitter.emit(str(msg_type), self, message)

    def wait_login(self, timeout=None):
        log.info("wait login...")
        self.__wait_login_event.wait(timeout)

    def open(self, smart=False):
        self.pid = wcprobe.open(smart)
        log.info("open wechat pid: %d", self.pid)
        return self.pid != 0

    def attach(self, pid: int):
        self.pid = pid
        log.info("attach wechat pid: %d", self.pid)
        return wcprobe.attach(pid)

    def detach(self):
        log.info("detach wechat pid: %d", self.pid)
        return wcprobe.detach(self.pid)

    def __send(self, msg_type, data=None, extend=None):
        if not self.login_status:
            raise WeChatNotLoginError()

        message = {
            'type': msg_type,
            'data': {} if data is None else data,
        }
        if extend is not None:
            message["extend"] = extend
        message_json = json.dumps(message)
        log.debug("communicate wechat pid:%d,  data: %s", self.pid, message)
        return wcprobe.send(self.client_id, message_json)

    def __send_sync(self, msg_type, data=None, timeout=10):
        req_data = ReqData(msg_type, data)
        extend = self.__new_extend()
        self.__req_data_cache[extend] = req_data
        self.__send(msg_type, data, extend)
        return req_data.wait_response(timeout)

    def __new_extend(self):
        while True:
            guid = generate_guid("req")
            if guid not in self.__req_data_cache:
                return guid

    def __repr__(self):
        return f"WeChatInstance(pid: {self.pid}, client_id: {self.client_id})"

    def get_login_info(self):
        """
        获取登录信息
        """
        return self.__login_info

    def get_self_info(self):
        """
        获取自己个人信息跟登录信息类似
        """
        return self.__send_sync(wx_type.MT_GET_SELF_MSG)

    def get_contacts(self):
        """
        获取联系人列表
        """
        return self.__send_sync(wx_type.MT_GET_CONTACTS_MSG)

    def get_contact_detail(self, wxid):
        data = {
            "wxid": wxid
        }
        return self.__send_sync(wx_type.MT_GET_CONTACT_DETAIL_MSG, data)

    def get_rooms(self):
        """
        获取群列表
        """
        return self.__send_sync(wx_type.MT_GET_ROOMS_MSG)

    def get_room_members(self, room_wxid: str):
        """
        获取群成员列表
        """
        data = {
            "room_wxid": room_wxid
        }
        return self.__send_sync(wx_type.MT_GET_ROOM_MEMBERS_MSG, data)

    def send_text(self, to_wxid: str, content: str):
        """
        发送文本消息
        """
        data = {
            "to_wxid": to_wxid,
            "content": content
        }
        return self.__send(wx_type.MT_SEND_TEXT_MSG, data)

    def send_room_at_msg(self, to_wxid: str, content: str, at_list: List[str]):
        """
        发送群@消息
        """
        data = {
            'to_wxid': to_wxid,
            'content': content,
            'at_list': at_list
        }
        return self.__send(wx_type.MT_SEND_ROOM_AT_MSG, data)

    def send_card(self, to_wxid: str, card_wxid: str):
        """
        发送名片
        """
        data = {
            'to_wxid': to_wxid,
            'card_wxid': card_wxid
        }
        return self.__send(wx_type.MT_SEND_CARD_MSG, data)

    def send_link_card(self, to_wxid: str, title: str, desc: str, url: str, image_url: str):
        """
        发送链接卡片
        """
        data = {
            'to_wxid': to_wxid,
            'title': title,
            'desc': desc,
            'url': url,
            'image_url': image_url
        }
        return self.__send(wx_type.MT_SEND_LINK_MSG, data)

    def send_image(self, to_wxid: str, file_path: str):
        """
        发送图片
        """
        data = {
            'to_wxid': to_wxid,
            'file': file_path
        }
        return self.__send(wx_type.MT_SEND_IMAGE_MSG, data)

    def send_file(self, to_wxid: str, file_path: str):
        """
        发送文件
        """
        data = {
            'to_wxid': to_wxid,
            'file': file_path
        }
        return self.__send(wx_type.MT_SEND_FILE_MSG, data)

    #
    def send_video(self, to_wxid: str, file_path: str):
        """
        发送视频
        """
        data = {
            'to_wxid': to_wxid,
            'file': file_path
        }
        return self.__send(wx_type.MT_SEND_VIDEO_MSG, data)

    # 发送gif
    def send_gif(self, to_wxid, file):
        data = {
            'to_wxid': to_wxid,
            'file': file
        }
        return self.__send(wx_type.MT_SEND_GIF_MSG, data)
