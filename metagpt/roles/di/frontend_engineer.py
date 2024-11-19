import asyncio

from metagpt.prompts.di.frontend_engineer import FE_EXAPMLE, FRONTEND_ENGINEER_PROMPT
from metagpt.roles.di.engineer2 import Engineer2

from metagpt.logs import logger

from metagpt.prompts.di.template import GENERAL_WEB_APP_TEMPLATE_PROMPT
from metagpt.schema import Message
from metagpt.tools.libs.search_template import TemplateInfo
from metagpt.tools.tool_registry import register_tool

from metagpt.schema import UserMessage

@register_tool(include_functions=["search_template"])
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
                "FrontendEngineer.search_template": self.search_template,
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
            result = await self.search_template(content)
            logger.info(f"Template search result: {result}")

            self.is_first_dev_request = False  # Update flag

        await self._format_instruction()
        res = await super()._think()
        return res

    def _retrieve_experience(self) -> str:
        return FE_EXAPMLE

    async def set_template(self, template_info: TemplateInfo = None, extra_user_info: str = None, extra_info: str = None) -> None:
        
        self._template_content = await self.template_tool.get_template_info(template_info)
        # Update template part in instruction
        self.instruction = self.instruction.replace(
            GENERAL_WEB_APP_TEMPLATE_PROMPT,
            self._template_content
        )

        content = f"{extra_info}\n\n{extra_user_info}"
        # Update memory
        self.rc.memory.add(UserMessage(content=content))
        logger.info(f"Template information, User info and extra info updated")

    def _is_business_card_requirement(self, requirement: str) -> bool:
        return "名片" in requirement or "business card" in requirement.lower()

    async def search_template(self, requirement: str) -> str:
        """Process template-related requirements

        Args:
            requirement: User requirement description
            template: Template information

        Returns:
            Processing result description
        """
        is_business_card_requirement = self._is_business_card_requirement(requirement)
        if not is_business_card_requirement:
            return "The requirement is not a business card requirement"

        # 1. Search for matching template
        template, extra_user_info = await self.template_tool.search(requirement)
        if not template:
            return "Can't find a matching template"

        target_dir = await self.template_tool.copy_template(template)

        extra_info = f"Successfully copied {template.style} template to {target_dir}, next step is to rename the template folder to the project name"
        # update template info
        await self.set_template(template, extra_user_info, extra_info)

        
        if not target_dir:
            return "Failed to copy template"

        return f"Successfully copied {template.style} template to {target_dir}, next step is to rename the template folder to the project name"
