import copy
import re
from pathlib import Path
from typing import Any, Dict, Tuple

from metagpt.actions import UserRequirement
from metagpt.actions.search_enhanced_qa import SearchEnhancedQA
from metagpt.prompts.di.frontend_engineer import FE_EXAPMLE, FRONTEND_ENGINEER_PROMPT
from metagpt.prompts.di.role_zero import QUICK_THINK_PROMPT, QUICK_RESPONSE_SYSTEM_PROMPT, QUICK_THINK_TAG
from metagpt.roles.di.engineer2 import Engineer2

from metagpt.logs import logger

from metagpt.prompts.di.template import GENERAL_WEB_APP_TEMPLATE
from metagpt.schema import Message, AIMessage
from metagpt.tools.libs.cr import CodeReview
from metagpt.tools.libs.git import git_create_pull
from metagpt.tools.libs.image_getter import ImageGetter
from metagpt.tools.libs.search_template import TemplateInfo
from metagpt.const import METAGPT_ROOT
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.common import any_to_str, awrite
from metagpt.utils.report import ThoughtReporter

from metagpt.schema import UserMessage


def read_file_by_path(file_path: Path) -> str:
    """读取文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._template_content = GENERAL_WEB_APP_TEMPLATE

    def _update_tool_execution(self):
        # validate = ValidateAndRewriteCode()
        cr = CodeReview()
        image_getter = ImageGetter()
        if self.run_eval is True:
            # Evalute tool map
            self.tool_execution_map.update(
                {
                    "git_create_pull": git_create_pull,
                    "Engineer2.write_new_code": self.write_new_code,
                    "ImageGetter.get_image": image_getter.get_image,
                    "CodeReview.review": cr.review,
                    "CodeReview.fix": cr.fix,
                    "Terminal.run_command": self._eval_terminal_run,
                    "RoleZero.ask_human": self._end,
                    "RoleZero.reply_to_human": self._end,
                    "Deployer.deploy_to_public": self._deploy_to_public,
                    "FrontendEngineer.handle_template": self.handle_template,
                }
            )
        else:
            # Default tool map
            self.tool_execution_map.update(
                {
                    "git_create_pull": git_create_pull,
                    "Engineer2.write_new_code": self.write_new_code,
                    "ImageGetter.get_image": image_getter.get_image,
                    "CodeReview.review": cr.review,
                    "CodeReview.fix": cr.fix,
                    "Terminal.run_command": self.terminal.run_command,
                    "Deployer.deploy_to_public": self._deploy_to_public,
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

        # flag = await self._is_development_request(send_msg)
        # logger.info(f"think: {send_msg}, {flag}")
        if self.is_first_dev_request:
            template_result = await self.handle_template(send_msg.content)
            logger.info(f"Template search result: {template_result}")
            self.is_first_dev_request = False  # Update flag

            # Update memory
            self.rc.memory.add(UserMessage(content=template_result))

        await self._format_instruction()
        res = await super()._think()
        return res


    async def update_search_template_tool(self, **kwargs) -> bool:
        """Updates SearchTemplate with some user defined information

        Args:
            **kwargs: User defined information

        Returns:
            bool: True if update succeeds, False otherwise.

        Raises:
            IOError: If file reading or writing operations fail.
            Exception: For any other unexpected errors.
        """
        try:
            # update rag top_k, check 'rag_top_k' where in kwargs
            if 'rag_top_k' in kwargs:
                rag_top_k = kwargs.get('rag_top_k')
                if isinstance(rag_top_k, int) and rag_top_k > 0:
                    if hasattr(self.template_tool, '_engine'):

                        logger.info(f"Updated RAG top_k to {rag_top_k}")
                else:
                    logger.warning(f"Invalid rag_top_k value: {rag_top_k}")

            return True

        except Exception as e:
            logger.error(f'Error applying user info: {str(e)}')
            return False

    def _retrieve_experience(self) -> str:
        return FE_EXAPMLE

    async def set_template(self, template_info: TemplateInfo=None) -> None:
        if template_info is not None:
            """Update template information to system prompt"""
            template_content = f"""
            ### Template Intro
            1. This is a template for {template_info.description}
            2. The template is at {METAGPT_ROOT}/workspace/template
            3. Required fields: {', '.join(template_info.required_fields)}
            4. Style your elements according to the template style: {template_info.style.value}

            ### Project Structure
            {self.template_tool._get_template_structure(template_info)}
            """
            self._template_content = template_content
            # Update template part in instruction
            self.instruction = self.instruction.replace(
                GENERAL_WEB_APP_TEMPLATE,
                self._template_content
            )
            logger.info(f"Template update successfully")


    async def handle_template(self, requirement: str, template: TemplateInfo=None) -> str:
        """Process template-related requirements

        Args:
            requirement: User requirement description

        Returns:
            Processing result description
        """
        try:
            # 1. Search for matching template
            template = await self.template_tool.search(requirement)
            if not template:
                return "Can't find a matching template"

            # 2. Apply template
            await self.set_template(template)

            success = await self.template_tool.copy_template(template)
            if not success:
                return "Failed to copy template"


            return f"Successfully copied {template.style.value} template, next step is to rename the template folder to the project name"

        except Exception as e:

            return f"Error during template processing: {str(e)}"
