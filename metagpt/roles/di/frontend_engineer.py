import os
from importlib.util import find_spec
from pathlib import Path

from pydantic import model_validator

from metagpt.const import METAGPT_ROOT
from metagpt.logs import logger
from metagpt.prompts.di.frontend_engineer import FE_EXAPMLE, FRONTEND_ENGINEER_PROMPT
from metagpt.prompts.di.template import GENERAL_WEB_APP_TEMPLATE_PROMPT
from metagpt.roles.di.engineer2 import Engineer2
from metagpt.schema import UserMessage
from metagpt.tools.libs.search_template import SearchTemplate, TemplateInfo
from metagpt.tools.tool_registry import register_tool


@register_tool(include_functions=["search_template"])
class FrontendEngineer(Engineer2):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_search_template_tool()

    def set_search_template_tool(self):
        is_not_empty_templates_path = (
            os.path.exists(Path(METAGPT_ROOT) / self.config.frontend_engineer_config.templates_path)
            and len(os.listdir(Path(METAGPT_ROOT) / self.config.frontend_engineer_config.templates_path)) > 0
        )
        is_installed_rag = self._check_rag_installed()

        if (
            self.config.frontend_engineer_config.enable_search_template
            and is_not_empty_templates_path
            and is_installed_rag
        ):
            self.tools.append("FrontendEngineer")

            self.template_tool = SearchTemplate(
                template_path=Path(METAGPT_ROOT) / self.config.frontend_engineer_config.templates_path
            )
            logger.info("FrontendEngineer tools set")
        else:
            logger.warning("FrontendEngineer tools not set")

    def _check_rag_installed(self) -> bool:
        """Check if RAG dependencies are installed"""
        return find_spec("llama_index") is not None

    @model_validator(mode="after")
    def _update_tool_execution(self) -> "FrontendEngineer":
        super()._update_tool_execution()
        self.tool_execution_map.update(
            {
                "FrontendEngineer.search_template": self.search_template,
            }
        )

    async def _think(self) -> bool:
        # Check if the latest message is a development request
        send_msg = self.rc.memory.get(-1)[0]

        if self.is_first_dev_request:
            content = send_msg.content.replace("[Message] from Mike to Alex: ", "")
            logger.info("First dev request, handle template")
            if self.template_tool:
                result = await self.search_template(content)
                logger.info(f"Template search result: {result}")
            else:
                logger.warning("Template tool not found, skip template search")

            self.is_first_dev_request = False  # Update flag

        await self._format_instruction()
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

        extra_info = f"Successfully copied {template.style} template to {target_dir}, next step is to rename the template folder to the project name. If NO additional user information has been provided, you should directly deploy the retrieved template without any modifications."
        # update template info
        await self.set_template(template, extra_user_info, extra_info)

        if not target_dir:
            return "Failed to copy template"

        return f"Successfully copied {template.style} template to {target_dir}, next step is to rename the template folder to the project name"
