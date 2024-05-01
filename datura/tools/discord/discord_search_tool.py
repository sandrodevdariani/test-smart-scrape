import json
import bittensor as bt
from typing import Type
from pydantic import BaseModel, Field
from starlette.types import Send
from datura.tools.base import BaseTool
from datura.services.discord_api_wrapper import DiscordAPIClient


class DiscordSearchToolSchema(BaseModel):
    query: str = Field(
        ...,
        description="The search query for Discord messages.",
    )


class DiscordSearchTool(BaseTool):
    """Tool that searches for messages in Discord based on a query."""

    name = "Discord Search"
    slug = "search_discord"
    description = "Search for messages in Discord for a given query."
    args_scheme: Type[DiscordSearchToolSchema] = DiscordSearchToolSchema
    tool_id = "dd29715f-066f-4f8d-8adb-2dd005380f03"

    def _run():
        pass

    async def _arun(
        self,
        query: str,
    ) -> str:
        """Search Discord messages and return results."""
        client = DiscordAPIClient()

        body = {
            "query": query,
            "limit": 10,
            "page": 1,
            "nest_level": 2,
            "only_parsable": True,
        }

        (result, _, _) = await client.search_messages(body)
        bt.logging.info(
            "================================== Discord Result ==================================="
        )
        bt.logging.info(result)
        bt.logging.info(
            "================================== Discord Result ===================================="
        )

        return result

    async def send_event(self, send: Send, response_streamer, data):
        if not data:
            return

        if data:
            messages_response_body = {
                "type": "discord_search",
                "content": data,
            }

            await send(
                {
                    "type": "http.response.body",
                    "body": json.dumps(messages_response_body).encode("utf-8"),
                    "more_body": False,
                }
            )
            bt.logging.info("Discord search results data sent")