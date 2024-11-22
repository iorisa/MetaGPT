from pydantic import model_validator

from metagpt.logs import logger
from metagpt.prompts.di.frontend_engineer import FE_EXAPMLE, FRONTEND_ENGINEER_PROMPT
from metagpt.prompts.di.template import GENERAL_WEB_APP_TEMPLATE_PROMPT
from metagpt.roles.di.engineer2 import Engineer2
from metagpt.schema import UserMessage
from metagpt.tools.libs.search_template import SearchTemplate, TemplateInfo


class FrontendEngineer(Engineer2):
    use_search_template: bool = True
    instruction: str = FRONTEND_ENGINEER_PROMPT
    template_tool: SearchTemplate = None
    tools: list[str] = [
        "Editor:read,write,edit_file_by_replace,insert_content_at_line,append_file",
        "RoleZero",
        "Terminal:run_command",
        "SearchEnhancedQA",
        "ImageGetter",
        "Deployer",
        "Engineer2",
    ]

    @model_validator(mode="after")
    def set_search_template_tool(self):
        if self.template_tool is None and self.use_search_template:
            self.template_tool = SearchTemplate()
            logger.info("FrontendEngineer tools set")
        else:
            logger.warning("FrontendEngineer tools not set")
        return self

    async def _think(self) -> bool:
        # Check if the latest message is a development request
        send_msg = self.rc.memory.get()

        if self.is_first_dev_request and len(send_msg) > 0:
            content = "\n".join([msg.content for msg in send_msg])
            content = content.replace("[Message] from Mike to Alex: ", "").replace("[Message] from User to Mike: ", "")
            logger.info("First dev request, handle template")
            if self.template_tool:
                result = await self.search_template(content)
                logger.info(f"Template search result: {result}")
            else:
                logger.warning("Template tool not found, skip template search")

            self.is_first_dev_request = False  # Update flag

        res = await super()._think()
        return res

    def _retrieve_experience(self) -> str:
        return FE_EXAPMLE

    async def set_template(
        self, template_info: TemplateInfo = None, extra_user_info: str = None, extra_info: str = None
    ) -> None:
        self._template_content = await self.template_tool.get_template_info(template_info)
        # Update template part in instruction
        self.instruction = self.instruction.replace(GENERAL_WEB_APP_TEMPLATE_PROMPT, self._template_content)

        content = f"{extra_info}\n\n{extra_user_info}"
        # Update memory
        self.rc.memory.add(UserMessage(content=content))
        logger.info(f"Template information, User info and extra info updated: \n{content}")

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
        if not template:
            return "Can't find a matching template"

        target_dir = await self.template_tool.copy_template(template)

        extra_info = f"Successfully copied {template.style} template to {target_dir}, {target_dir} is the project root path. next step is to rename the template folder to the project name. If NO additional user information has been provided, you should directly deploy the retrieved template without any modifications."
        # update template info
        await self.set_template(template, extra_user_info, extra_info)

        if not target_dir:
            return "Failed to copy template"

        return f"Successfully copied {template.style} template to {target_dir}, next step is to rename the template folder to the project name"
