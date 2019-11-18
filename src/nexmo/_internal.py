"""
This module contains implementations of Nexmo Server SDK internals.
Their interfaces are unstable and should not be relied upon.

"""
from enum import Enum
import jwt
import logging
import time
from uuid import uuid4

from requests.sessions import Session

from .errors import AuthenticationError, ClientError, ServerError

try:
    from json import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError

logger = logging.getLogger("nexmo")


class Order(Enum):
    ASC = "asc"
    DESC = "desc"


class BasicAuthenticatedServer(object):
    def __init__(self, host, user_agent, api_key, api_secret):
        self.host = host
        self._session = session = Session()
        session.auth = (api_key, api_secret)  # Basic authentication.
        session.headers.update({"User-Agent": user_agent})

    def _uri(self, path):
        return "{host}{path}".format(host=self.host, path=path)

    def get(self, path, params=None, headers=None):

        return self._parse(
            self._session.get(self._uri(path), params=params, headers=headers)
        )

    def post(self, path, body=None, headers=None):
        return self._parse(
            self._session.post(self._uri(path), json=body, headers=headers)
        )

    def put(self, path, body=None, headers=None):
        return self._parse(
            self._session.put(self._uri(path), json=body, headers=headers)
        )

    def delete(self, path, body=None, headers=None):
        return self._parse(
            self._session.delete(self._uri(path), json=body, headers=headers)
        )

    def _parse(self, response):
        logger.debug("Response headers %r", response.headers)
        if response.status_code == 401:
            raise AuthenticationError()
        elif response.status_code == 204:
            return None
        elif 200 <= response.status_code < 300:
            return response.json()
        elif 400 <= response.status_code < 500:
            logger.warning(
                "Client error: %s %r", response.status_code, response.content
            )
            message = "{code} response".format(code=response.status_code)
            # Test for standard error format:
            try:
                error_data = response.json()
                if (
                    "type" in error_data
                    and "title" in error_data
                    and "detail" in error_data
                ):
                    message = "{title}: {detail} ({type})".format(
                        title=error_data["title"],
                        detail=error_data["detail"],
                        type=error_data["type"],
                    )
            except JSONDecodeError:
                pass
            raise ClientError(message)
        elif 500 <= response.status_code < 600:
            logger.warning(
                "Server error: %s %r", response.status_code, response.content
            )
            message = "{code} response".format(code=response.status_code)
            raise ServerError(message)


class JWTAuthenticatedServer(object):
    def __init__(self, host, user_agent, application_id, private_key):
        self.host = host
        self.application_id = application_id
        self.private_key = private_key
        self.auth_params = {}
        self._session = session = Session()
        session.headers.update({"User-Agent": user_agent})

    def _uri(self, path):
        return "{host}{path}".format(host=self.host, path=path)

    def get(self, path, params=None, headers=None):
        return self._parse(
            self._session.get(
                self._uri(path), params=params, headers=self._headers(headers)
            )
        )

    def post(self, path, body=None, headers=None):
        return self._parse(
            self._session.post(
                self._uri(path), json=body, headers=self._headers(headers)
            )
        )

    def put(self, path, body=None, headers=None):
        return self._parse(
            self._session.put(
                self._uri(path), json=body, headers=self._headers(headers)
            )
        )

    def delete(self, path, body=None, headers=None):
        return self._parse(
            self._session.delete(
                self._uri(path), json=body, headers=self._headers(headers)
            )
        )

    def _headers(self, headers):
        if headers is None:
            headers = {"Accept": "application/json"}
        token = self.generate_application_jwt()
        return dict(headers, Authorization=b"Bearer " + token)

    def generate_application_jwt(self, when=None):
        if self.private_key is None:
            raise ClientError(
                "private_key must be provided to call JWT-authenticated methods."
            )

        iat = int(when if when is not None else time.time())

        payload = dict(self.auth_params)
        payload.setdefault("application_id", self.application_id)
        payload.setdefault("iat", iat)
        payload.setdefault("exp", iat + 60)
        payload.setdefault("jti", str(uuid4()))

        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def _parse(self, response):
        logger.debug("Response headers %r", response.headers)
        if response.status_code == 401:
            raise AuthenticationError()
        elif response.status_code == 204:
            return None
        elif 200 <= response.status_code < 300:
            return response.json()
        elif 400 <= response.status_code < 500:
            logger.warning(
                "Client error: %s %r", response.status_code, response.content
            )
            message = "{code} response".format(code=response.status_code)
            # Test for standard error format:
            try:
                error_data = response.json()
                if (
                    "type" in error_data
                    and "title" in error_data
                    and "detail" in error_data
                ):
                    message = "{title}: {detail} ({type})".format(
                        title=error_data["title"],
                        detail=error_data["detail"],
                        type=error_data["type"],
                    )
                elif "code" in error_data and "description" in error_data:
                    message = "({code}) {description}".format(
                        code=error_data["code"], description=error_data["description"]
                    )

            except JSONDecodeError:
                pass
            raise ClientError(message)
        elif 500 <= response.status_code < 600:
            logger.warning(
                "Server error: %s %r", response.status_code, response.content
            )
            message = "{code} response".format(code=response.status_code)
            raise ServerError(message)


class ApplicationV2(object):
    """
    Provides Application API v2 functionality.

    Don't instantiate this class yourself, access it via :py:attr:`nexmo.Client.application_v2`
    """

    def __init__(self, api_server):
        self._api_server = api_server

    def create_application(self, application_data):
        """
        Create an application using the provided `application_data`.

        :param dict application_data: A JSON-style dict describing the application to be created.

        >>> client.application_v2.create_application({ 'name': 'My Cool App!' })

        Details of the `application_data` dict are described at https://developer.nexmo.com/api/application.v2#createApplication
        """
        return self._api_server.post("/v2/applications", application_data)

    def get_application(self, application_id):
        """
        Get application details for the application with `application_id`.

        The format of the returned dict is described at https://developer.nexmo.com/api/application.v2#getApplication

        :param str application_id: The application ID.
        :rtype: dict
        """

        return self._api_server.get(
            "/v2/applications/{application_id}".format(application_id=application_id),
            headers={"content-type": "application/json"},
        )

    def update_application(self, application_id, params):
        """
        Update the application with `application_id` using the values provided in `params`.
        """
        return self._api_server.put(
            "/v2/applications/{application_id}".format(application_id=application_id),
            params,
        )

    def delete_application(self, application_id):
        """
        Delete the application with `application_id`.
        """

        self._api_server.delete(
            "/v2/applications/{application_id}".format(application_id=application_id),
            headers={"content-type": "application/json"},
        )

    def list_applications(self, page_size=None, page=None):
        """
        List all applications for your account.

        Results are paged, so each page will need to be requested to see all applications.

        :param int page_size: The number of items in the page to be returned
        :param int page: The page number of the page to be returned.
        """
        params = _filter_none_values({"page_size": page_size, "page": page})

        return self._api_server.get(
            "/v2/applications",
            params=params,
            headers={"content-type": "application/json"},
        )


class Conversation(object):
    """
    Provides Conversation API functionality.

    Don't instantiate this class yourself, access it via :py:attr:`nexmo.Client.conversation`
    """

    def __init__(self, api_server):
        self._api_server = api_server

    def create_conversation(self, conversation_data):
        """
        Create a new conversation.

        See https://developer.nexmo.com/api/conversation#createConversation for details.

        :param conversation_data: A dict containing the request body configuration for the conversation to be created.
        """
        return self._api_server.post("/v0.1/conversations", conversation_data)

    def list_conversations(self, page_size=None, order=None, cursor=None):
        """
        List all, or a filtered set, of conversations.

        Only a summary of conversation data is provided.
        Once you've identified the conversation you need to work with, use :py:func: #get_conversation: to fetch all of the conversation details.

        See https://developer.nexmo.com/api/conversation#get-conversations for details.

        :param int page_size: The number of items in the page to be returned
        :param str order: Sort the conversations by date created. Either 'asc' or 'desc'.
        :param str cursor: The identifier needed to request the page.
        """
        if order is not None and not isinstance(order, Order):
            raise ClientError("order should be an instance of the Order enum.")

        params = _filter_none_values(
            {"page_size": page_size, "order": order and order.value, "cursor": cursor}
        )
        return self._api_server.get("/v0.1/conversations", params=params)

    def update_conversation(self, conversation):
        """
        Update a conversation, specified by the 'id' attribute in the supplied 'conversation' dict.

        See https://developer.nexmo.com/api/conversation#update-conversation for details.

        :param conversation: A dict containing the conversation details to be updated.
        """
        conversation_id = conversation.pop("id")
        path = "/v0.1/conversations/{conversation_id}".format(
            conversation_id=conversation_id
        )
        return self._api_server.put(path, conversation)

    def get_conversation(self, conversation_id):
        """
        Get all details of a conversation.

        See https://developer.nexmo.com/api/conversation#get-conversation for details.

        :param str conversation_id: The id of the conversation to be returned.
        """
        path = "/v0.1/conversations/{conversation_id}".format(
            conversation_id=conversation_id
        )
        return self._api_server.get(path)

    def delete_conversation(self, conversation_id):
        """
        Delete the conversation identified by 'conversation_id'.
        """
        path = "/v0.1/conversations/{conversation_id}".format(
            conversation_id=conversation_id
        )
        return self._api_server.delete(path, headers={})

    def list_users(self):
        """
        List all, or a filtered set, of users.

        See https://developer.nexmo.com/api/conversation#get-users for details.

        :param int page_size: The number of items in the page to be returned
        :param str order: Sort the users by date created. Either 'asc' or 'desc'.
        :param str cursor: The identifier needed to request a page.
        """
        return self._api_server.get("/v0.1/users")

    def create_user(self, user_data):
        """
        Create a new user.

        See https://developer.nexmo.com/api/conversation#create-user for details.

        :param user_data: A dict containing configuration for the new user.
        """
        return self._api_server.post("/v0.1/users", user_data)

    def get_user(self, user_id):
        """
        Get a single user.

        See https://developer.nexmo.com/api/conversation#get-user for details.

        :param str user_id: The ID of the user to be returned.
        """
        path = "/v0.1/users/{user_id}".format(user_id=user_id)
        return self._api_server.get(path)

    def update_user(self, user_data):
        """
        Update a user record, identified by the 'id' attribute in 'user_data'.

        See https://developer.nexmo.com/api/conversation#update-user for details.

        :param dict user_data: A dict containing user data attributes to be updated.
        """
        user_id = user_data.pop("id")
        path = "/v0.1/users/{user_id}".format(user_id=user_id)
        return self._api_server.put(path, user_data)

    def delete_user(self, user_id):
        """
        Delete a user identified by 'user_id'.

        See https://developer.nexmo.com/api/conversation#delete-user for details.

        :param str user_id: The id of the user to be deleted.
        """
        path = "/v0.1/users/{user_id}".format(user_id=user_id)
        return self._api_server.delete(path, headers={})

    def create_member(self, conversation_id, body):
        """
        Create a member by attaching a user to a conversation.

        See https://developer.nexmo.com/api/conversation#create-member for details.

        :param str conversation_id: The id of the conversation to attach the user to.
        :param dict body: Configuration describing how the user is to be attached to the conversation.
        """
        path = "/v0.1/conversations/{conversation_id}/members".format(
            conversation_id=conversation_id
        )
        return self._api_server.post(path, body)

    def list_members(self, conversation_id, page_size=None, order=None, cursor=None):
        """
        List the members of a conversation.

        See https://developer.nexmo.com/api/conversation#get-members for details.

        :param int page_size: The number of items in the page to be returned
        :param str order: Sort the entries by date created. Either 'asc' or 'desc'.
        :param str cursor: The identifier needed to request a page.
        """
        path = "/v0.1/conversations/{conversation_id}/members".format(
            conversation_id=conversation_id
        )
        params = _filter_none_values(
            {"page_size": page_size, "order": order and order.value, "cursor": cursor}
        )
        return self._api_server.get(path, params=params)

    def get_member(self, conversation_id, member_id):
        """
        Get the details of a conversation's member.

        See https://developer.nexmo.com/api/conversation#get-member for details.

        :param str conversation_id: The id of the conversation the member belongs to.
        :param str member_id: The id of the member.
        """
        path = "/v0.1/conversations/{conversation_id}/members/{member_id}".format(
            conversation_id=conversation_id, member_id=member_id
        )
        return self._api_server.get(path)

    def update_member(self, conversation_id, member_id, body):
        """
        Update the details of a conversation's member.

        See https://developer.nexmo.com/api/conversation#update-member for details.

        :param str conversation_id: The id of the conversation the member belongs to.
        :param str member_id: The id of the member.
        :param dict body: A dict containing the member's configuration to be updated.
        """
        path = "/v0.1/conversations/{conversation_id}/members/{member_id}".format(
            conversation_id=conversation_id, member_id=member_id
        )
        return self._api_server.put(path)

    def delete_member(self, conversation_id, member_id):
        """
        Remove a user from a conversation.

        See https://developer.nexmo.com/api/conversation#delete-member for details.

        :param str conversation_id: The id of the conversation the member belongs to.
        :param str member_id: The id of the member.
        """
        path = "/v0.1/conversations/{conversation_id}/members/{member_id}".format(
            conversation_id=conversation_id, member_id=member_id
        )
        return self._api_server.delete(path, headers={})

    def create_event(self, conversation_id, event_data):
        """
        Fire an event to members of the conversation.

        See https://developer.nexmo.com/api/conversation#create-event for details.

        :param str conversation_id: The id of the conversation the event belongs to.
        :param dict event_data: The details of the event.
        """
        path = "/v0.1/conversations/{conversation_id}/events".format(
            conversation_id=conversation_id
        )
        return self._api_server.post(path, event_data)

    def list_events(self, conversation_id, start_id=None, end_id=None):
        """
        List the events in a conversation.

        See https://developer.nexmo.com/api/conversation#get-events for details.

        :param str start_id: The first event id to be returned.
        :param str end_id: The last event id to be returned.

        """
        params = _filter_none_values({"start_id": start_id, "end_id": end_id})
        path = "/v0.1/conversations/{conversation_id}/events".format(
            conversation_id=conversation_id
        )
        return self._api_server.get(path, params=params)

    def get_event(self, conversation_id, event_id):
        """
        Get the details of an event.

        See https://developer.nexmo.com/api/conversation#get-event for details.

        :param str conversation_id: The id of the conversation the event belongs to.
        :param str event_id: The id of the event.
        """
        path = "/v0.1/conversations/{conversation_id}/events/{event_id}".format(
            conversation_id=conversation_id, event_id=event_id
        )
        return self._api_server.get(path)

    def delete_event(self, conversation_id, event_id):
        """
        Delete an event.

        See https://developer.nexmo.com/api/conversation#delete-event for details.

        :param str conversation_id: The id of the conversation the event belongs to.
        :param str event_id: The id of the event.
        """
        path = "/v0.1/conversations/{conversation_id}/events/{event_id}".format(
            conversation_id=conversation_id, event_id=event_id
        )
        return self._api_server.delete(path, headers={})


def _filter_none_values(d):
    """
    A convenient one-liner to remove items from a dict where the values are None.
    """
    return {k: v for k, v in d.items() if v is not None}


def _format_date_param(params, key, format="%Y-%m-%d %H:%M:%S"):
    """
    Utility function to convert datetime values to strings.

    If the value is already a str, or is not in the dict, no change is made.

    :param params: A `dict` of params that may contain a `datetime` value.
    :param key: The datetime value to be converted to a `str`
    :param format: The `strftime` format to be used to format the date. The default value is '%Y-%m-%d %H:%M:%S'
    """
    if key in params:
        param = params[key]
        if hasattr(param, "strftime"):
            params[key] = param.strftime(format)