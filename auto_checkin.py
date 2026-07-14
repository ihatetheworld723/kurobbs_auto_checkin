import os
import sys
import hashlib, time, random
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from loguru import logger
from pydantic import BaseModel, Field

from ext_notification import send_notification


class Response(BaseModel):
    code: int = Field(..., alias="code", description="返回值")
    msg: str = Field(..., alias="msg", description="提示信息")
    success: Optional[bool] = Field(None, alias="success", description="token有时才有")
    data: Optional[Any] = Field(None, alias="data", description="请求成功才有")


class KurobbsClientException(Exception):
    """Custom exception for Kurobbs client errors."""
    pass


class KurobbsClient:
    FIND_ROLE_LIST_API_URL = "https://api.kurobbs.com/user/role/findRoleList"
    SIGN_URL = "https://api.kurobbs.com/encourage/signIn/v2"
    USER_SIGN_URL = "https://api.kurobbs.com/user/signIn"
    FORUM_LIST_URL = "https://api.kurobbs.com/forum/list"
    LIKE_URL = "https://api.kurobbs.com/forum/like"
    GET_POST_DETAIL_URL = "https://api.kurobbs.com/forum/getPostDetail"
    SHARE_TASK_URL = "https://api.kurobbs.com/encourage/level/shareTask"

    def __init__(self, token: str, uid: str):
        self.uid = uid
        self.token = token
        self.result: Dict[str, str] = {}
        self.exceptions: List[Exception] = []
        self.devcode = self.generate_fixed_string(uid)

    def generate_fixed_string(self, input_string, length=40):
        if not input_string:
            logger.warning("生成固定字符串输入为空, 使用默认值 1")
            input_string = "1"
        
        input_string = str(input_string)

        if length > 64:
            logger.warning(f"使用 {input_string} 生成长度 {length} 超过最大值, 已自动调整为64")
            length = 64

        sha256_hash = hashlib.sha256(input_string.encode('utf-8')).hexdigest().upper()
        fixed_string = sha256_hash[:length]

        logger.debug(f"使用 {input_string} 生成长度为 {length} 的固定字符串 {fixed_string}")
        return fixed_string

    def get_headers(self) -> Dict[str, str]:
        """Get the headers required for API requests."""
        return {
            "devcode": self.devcode,
            "source": "h5",
            "version": "3.1.3",
            "token": self.token,
            "Host": "api.kurobbs.com",
            "Origin": "https://www.kurobbs.com",
            "Referer": "https://www.kurobbs.com/",
            "content-type": "application/x-www-form-urlencoded; charset=utf-8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        }

    def make_request(self, url: str, data: Dict[str, Any]) -> Response:
        """Make a POST request to the specified URL with the given data."""
        headers = self.get_headers()
        response = requests.post(url, headers=headers, data=data)
        res = Response.model_validate_json(response.content)
        logger.debug(res.model_dump_json(indent=2, exclude={"data"}))
        return res

    def get_user_game_list(self, game_id: int) -> List[Dict[str, Any]]:
        """Get the list of games for the user."""
        data = {"gameId": game_id}
        res = self.make_request(self.FIND_ROLE_LIST_API_URL, data)
        return res.data
    
    def get_forum_list(self) -> Response:
        """Perform the get_forum_list operation."""
        user_game_list = self.get_user_game_list(3)
        gameId = user_game_list[0].get("gameId", 2)
        forumId = 2 if gameId == 2 else 9
        data = {
            "forumId": forumId,
            "gameId": gameId,
            "pageIndex": 1,
            "pageSize": 20,
            "searchType": 2,
            "timeType": 0,
            "topicId": 0,
        }
        return self.make_request(self.FORUM_LIST_URL, data)
    
    def get_post_detail(self, rsp_forumList: Response, post_index: int) -> Response:
        """Perform the get_post_detail operation."""
        data = {
            "isOnlyPublisher": 0,
            "postId": rsp_forumList.data["postList"][post_index]["postId"],
            "showOrderType": 2,
        }
        return self.make_request(self.GET_POST_DETAIL_URL, data)
    
    def like_post(self, rsp_PostDetail: Response, operateType: int=1) -> Response:
        """Perform the like_post operation."""
        data = {
            "forumId": rsp_PostDetail.data["postDetail"]["gameForumId"],
            "gameId": rsp_PostDetail.data["gameId"],
            "likeType": 1,
            "operateType": operateType,
            "postCommentId": 0,
            "postCommentReplyId": 0,
            "postId": rsp_PostDetail.data["postDetail"]["id"],
            "postType": rsp_PostDetail.data["postDetail"]["postType"],
            "toUserId": rsp_PostDetail.data["postDetail"]["postUserId"],
        }
        return self.make_request(self.LIKE_URL, data)
    
    def share_post(self, rsp_PostDetail: Response) -> Response:
        """Perform the share_post operation."""
        data = {
            "gameId": rsp_PostDetail.data["gameId"],
        }
        return self.make_request(self.SHARE_TASK_URL, data)
    
    def forum_task(self):
        """Perform the forum_task operation."""
        rsp_forumList = self.get_forum_list()
        if not rsp_forumList.success:
            failure_message = '获取帖子列表失败'
            self.exceptions.append(KurobbsClientException(f'{failure_message}, {rsp_forumList.msg}'))
            return
        self.result['get_forum_list'] = '获取帖子列表成功'
        success = 0
        for i in range(0, 5):
            rsp_getPostDetail = self.get_post_detail(rsp_forumList, i)
            if rsp_getPostDetail.success:
                success += 1
            time.sleep(random.uniform(1.0, 2.0))
            if success >= 3:
                break
        else:
            failure_message = '获取帖子详情失败'
            self.exceptions.append(KurobbsClientException(f'{failure_message}, {rsp_getPostDetail.msg}'))
            return
        self.result['get_post_detail'] = '获取帖子详情成功'
        success = 0
        for _ in range(0, 1):
            rsp_share_post = self.share_post(rsp_getPostDetail)
            if rsp_share_post.success:
                success += 1
            time.sleep(random.uniform(1.0, 2.0))
            if success >= 1:
                break
        else:
            failure_message = '分享帖子失败'
            self.exceptions.append(KurobbsClientException(f'{failure_message}, {rsp_share_post.msg}'))
            return
        self.result['share_post'] = '分享帖子成功'
        like_post = True
        success = 0
        for _ in range(0, 9):
            if like_post:
                rsp_like_post = self.like_post(rsp_getPostDetail, 1)
            if rsp_like_post.success:
                time.sleep(random.uniform(1.0, 2.0))
                like_post = False
                rsp_dislike_post = self.like_post(rsp_getPostDetail, 2)
                if rsp_dislike_post.success:
                    success += 1
                    like_post = True
            time.sleep(random.uniform(1.0, 2.0))
            if success >= 5:
                break
        else:
            failure_message = '点赞帖子失败'
            self.exceptions.append(KurobbsClientException(f'{failure_message}, {rsp_like_post.msg}'))
            return
        self.result['rsp_like_post'] = '点赞帖子成功'

    def checkin(self) -> Response:
        """Perform the check-in operation."""
        user_game_list = self.get_user_game_list(3)

        # 获取北京时间（UTC+8）
        beijing_tz = ZoneInfo('Asia/Shanghai')
        beijing_time = datetime.now(beijing_tz)
        data = {
            "gameId": user_game_list[0].get("gameId", 2),
            "serverId": user_game_list[0].get("serverId", None),
            "roleId": user_game_list[0].get("roleId", 0),
            "userId": user_game_list[0].get("userId", 0),
            "reqMonth": f"{beijing_time.month:02d}",
        }
        return self.make_request(self.SIGN_URL, data)

    def sign_in(self) -> Response:
        """Perform the sign-in operation."""
        return self.make_request(self.USER_SIGN_URL, {"gameId": 2})

    def _process_sign_action(
            self,
            action_name: str,
            action_method: Callable[[], Response],
            success_message: str,
            failure_message: str,
    ):
        """
        Handle the common logic for sign-in actions.

        :param action_name: The name of the action (used to store the result).
        :param action_method: The method to call for the sign-in action.
        :param success_message: The message to log on success.
        :param failure_message: The message to log on failure.
        """
        resp = action_method()
        logger.debug(resp)
        if resp.success:
            self.result[action_name] = success_message
        else:
            self.exceptions.append(KurobbsClientException(f'{failure_message}, {resp.msg}'))

    def start(self):
        """Start the sign-in process."""
        self._process_sign_action(
            action_name="checkin",
            action_method=self.checkin,
            success_message="签到奖励签到成功",
            failure_message="签到奖励签到失败",
        )

        self._process_sign_action(
            action_name="sign_in",
            action_method=self.sign_in,
            success_message="社区签到成功",
            failure_message="社区签到失败",
        )
        
        self.forum_task()

        self._log()

    @property
    def msg(self):
        return ", ".join(self.result.values()) + "!"

    def _log(self):
        """Log the results and raise exceptions if any."""
        if msg := self.msg:
            logger.info(msg)
        if self.exceptions:
            raise KurobbsClientException("; ".join(map(str, self.exceptions)))


def configure_logger(debug: bool = False):
    """Configure the logger based on the debug mode."""
    logger.remove()  # Remove default logger configuration
    log_level = "DEBUG" if debug else "INFO"
    logger.add(sys.stdout, level=log_level)


def main():
    """Main function to handle command-line arguments and start the sign-in process."""
    uid = os.getenv("UID")
    token = os.getenv("TOKEN")
    debug = os.getenv("DEBUG", False)
    configure_logger(debug=debug)

    try:
        kurobbs = KurobbsClient(token, uid)
        kurobbs.start()
        if kurobbs.msg:
            send_notification(kurobbs.msg)
    except KurobbsClientException as e:
        logger.error(str(e), exc_info=False)
        send_notification(str(e))
        sys.exit(1)
    except Exception as e:
        logger.exception("An unexpected error occurred:")
        sys.exit(1)


if __name__ == "__main__":
    main()

