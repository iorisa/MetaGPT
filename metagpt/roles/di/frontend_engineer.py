import asyncio
import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

from metagpt.prompts.di.frontend_engineer import FE_EXAPMLE, FRONTEND_ENGINEER_PROMPT
from metagpt.roles.di.engineer2 import Engineer2

from metagpt.logs import logger

from metagpt.prompts.di.template import GENERAL_WEB_APP_TEMPLATE
from metagpt.schema import Message
from metagpt.tools.libs.cr import CodeReview
from metagpt.tools.libs.git import git_create_pull
from metagpt.tools.libs.image_getter import ImageGetter
from metagpt.tools.libs.search_template import TemplateInfo
from metagpt.const import METAGPT_ROOT
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.common import CodeParser

from metagpt.schema import UserMessage

@register_tool(include_functions=["handle_template"])
class FrontendEngineer(Engineer2):
    instruction: str = FRONTEND_ENGINEER_PROMPT
    tools: list[str] = [
        "Editor:read,write,edit_file_by_replace,insert_content_at_line,append_file",
        "RoleZero",
        "Terminal:run_command",
        "SearchEnhancedQA",
        "ImageGetter",
        "Deployer",
        "Engineer2",
        "FrontendEngineer"
    ]

    def _update_tool_execution(self):
        super()._update_tool_execution()
        self.tool_execution_map.update(
            {
                "FrontendEngineer.handle_template": self.handle_template,
            }
        )

    def _get_latest_message(self) -> Message:
        for msg in self.rc.memory.get():
            if "Alex" in msg.send_to:
                return msg
        return None

    async def _think(self) -> bool:
        # Check if the latest message is a development request
        send_msg = self._get_latest_message()

        if self.is_first_dev_request:
            content = send_msg.content.replace("[Message] from Mike to Alex: ", "")
            logger.info(f"First dev request, handle template")
            # extrac user info
            # user_info = await self.extract_user_info(content)

            # logger.info(f"User info: {user_info}")
            result = await self.handle_template(content)
            logger.info(f"Template search result: {result}")

            # content = "This is First Dev Request, I have already handled the template, now I will start to develop the project. \n\nThe following is the template information and user information.\n\n"
            # content += f"{content}\n\n{result}\n\nUser info: {user_info}"
            content = "This is First Dev Request, I have already handled the template, now I will start to develop the project. \n\nThe following is the template information.\n\n"
            content += f"{content}\n\n{result}\n\n"
            # Update memory
            self.rc.memory.add(UserMessage(content=content))
            logger.info(f"First dev request, memory updated")
            self.is_first_dev_request = False  # Update flag

        await self._format_instruction()
        res = await super()._think()
        return res

    def _retrieve_experience(self) -> str:
        return FE_EXAPMLE

    async def set_template(self, template_info: TemplateInfo = None) -> None:
        
        self._template_content = await self.template_tool.get_template_info(template_info)
        # Update template part in instruction
        self.instruction = self.instruction.replace(
            GENERAL_WEB_APP_TEMPLATE,
            self._template_content
        )
        logger.info(f"Template update successfully")

    async def handle_template(self, requirement: str) -> str:
        """Process template-related requirements

        Args:
            requirement: User requirement description
            template: Template information

        Returns:
            Processing result description
        """
        # 1. Search for matching template
        template = await self.template_tool.search(requirement)
        if not template:
            return "Can't find a matching template"

        # update template info
        await self.set_template(template)

        target_dir = await self.template_tool.copy_template(template)
        if not target_dir:
            return "Failed to copy template"

        return f"Successfully copied {template.style} template to {target_dir}, next step is to rename the template folder to the project name"
