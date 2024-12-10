import os
import subprocess

# from agentops import track_agent
from pydantic import model_validator

from metagpt.logs import logger
from metagpt.prompts.di.frontend_engineer import FE_EXAPMLE, FRONTEND_ENGINEER_PROMPT
from metagpt.prompts.di.template import (
    EXRTA_INFO_PROMPT,
    GENERAL_WEB_APP_TEMPLATE_PROMPT,
)
from metagpt.roles.di.engineer2 import Engineer2
from metagpt.schema import UserMessage
from metagpt.tools.libs.search_template import BaseSearchTemplate, FixedSearchTemplate

_ = FixedSearchTemplate  # avoid pre-commit error


# @track_agent("FrontendEngineer")
class FrontendEngineer(Engineer2):
    instruction: str = FRONTEND_ENGINEER_PROMPT
    tools: list[str] = [
        "Editor:read,write,edit_file_by_replace,append_file",
        "RoleZero",
        "Terminal:run_command",
        "SearchEnhancedQA",
        "Deployer",
        "Engineer2",
        "Browser:click,goto,scroll",
    ]

    # Regarding template use:
    # 1. Set use_search_template to False to disable template
    # 2. Set template_tool to FixedSearchTemplate() to skip RAG and use a fixed template
    # 3. Set template_tool to None (unchanged) or SearchTemplate() to perform a full template search
    use_search_template: bool = True
    is_first_dev_request: bool = True
    template_tool: BaseSearchTemplate = None

    @model_validator(mode="after")
    def set_search_template_tool(self):
        if self.template_tool is None and self.use_search_template:
            # self.template_tool = SearchTemplate()
            self.template_tool = FixedSearchTemplate()
            logger.info("SearchTemplate set")
        else:
            logger.warning("SearchTemplate not set")
        return self

    async def _think(self) -> bool:
        # Check if the latest message is a development request
        send_msg = self.rc.memory.get()

        if self.is_first_dev_request and len(send_msg) > 0:
            self.is_first_dev_request = False  # Update flag
            content = "\n".join(
                [msg.content for msg in send_msg if self.name in msg.send_to or "UserRequirement" in msg.cause_by]
            )
            # content = content.replace("[Message] from Mike to Alex: ", "").replace("[Message] from User to Mike: ", "")
            content = content.replace("Mike", "Team Leader").replace("Alex", "Engineer")
            logger.info("First dev request, handle template")
            if self.template_tool:
                await self.search_template(content)
            else:
                logger.warning("Template tool not found, skip template search")

        res = await super()._think()

        return res

    def _retrieve_experience(self) -> str:
        return FE_EXAPMLE

    async def set_template(self, template_info: str = "", extra_user_info: str = None, extra_info: str = None) -> None:
        # Update template part in instruction
        self.instruction = self.instruction.replace(GENERAL_WEB_APP_TEMPLATE_PROMPT, template_info)

        content = extra_info
        if extra_user_info:
            content = f"Additional information provided by the user:{extra_user_info}\n\n{content}"
        # Update memory
        self.rc.memory.add(UserMessage(content=content))
        logger.info("Template information, User info and extra info updated")

    async def search_template(self, requirement: str) -> str:
        """Process template-related requirements

        Args:
            requirement: User requirement description
            template: Template information

        Returns:
            Processing result description
        """

        # 1. Search for matching template
        template, extra_user_info = await self.template_tool.search(requirement)
        if template:
            target_dir = await self.template_tool.copy_template(template.template_path, template.style)
            # install dependencies for JavaScript-based projects
            if os.path.exists(f"{target_dir}/package.json"):
                cmd = f"cd {target_dir} && pnpm i"
                subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            template_info = await self.template_tool.get_template_info(template)
            extra_info = EXRTA_INFO_PROMPT.format(template_style=template.style, target_dir=target_dir)
            await self.set_template(template_info, extra_user_info, extra_info)

            return target_dir
        else:
            return ""
