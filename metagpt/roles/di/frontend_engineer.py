import asyncio
import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

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

@register_tool(include_functions=["handle_template", "extract_user_info"])
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
                    "FrontendEngineer.extract_user_info": self.extract_user_info,
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
                    "FrontendEngineer.extract_user_info": self.extract_user_info,
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
            logger.info(f"First dev request, handle template")
            result = await self.handle_template(send_msg.content)
            if isinstance(result, tuple):
                template_result, user_info = result
            else:
                template_result, user_info = result, None
            logger.info(f"Template search result: {template_result}")

            content = "This is First Dev Request, I have already handled the template, now I will start to develop the project. \n\nThe following is the template information and user information.\n\n"
            content += f"{content}\n\n{template_result}\n\nUser info: {user_info}"
            # Update memory
            self.rc.memory.add(UserMessage(content=content))
            logger.info(f"First dev request, memory updated")
            self.is_first_dev_request = False  # Update flag

        await self._format_instruction()
        res = await super()._think()
        return res

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
            4. Style your elements according to the template style: {template_info.style}

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

    async def extract_user_info(self, user_input: str) -> Dict[str, Any]:
        """Extract user information from user_info with LLM"""
        required_fields = self.template_tool.get_required_fields()
        required_fields_str = ", ".join(required_fields)
        prompt = f"""
        ## Task
        Please extract the following information from the requirement
        ### Required fields
        {required_fields_str}
        ### User Input
        {user_input}

        ### User Information
        Please return the value of the missing fields in JSON format.
        ```json
        {{
            "user_info": {{
                "name": "value1",
                "job_title": "value2",
                "email": "value3",
                "phone": "value4",
                "brief_description": "value5",
                "MBTI": "value6",
                ...
            }}
        }}
        ```
        """
        logger.info(f"Extracting user info from: {user_input}")
        num = 0
        while num < 3:
            user_info = await self.llm.aask(prompt)
            # parse json
            user_info = user_info.replace("```json", "").replace("```", "").strip("\n")
            user_info = json.loads(user_info)["user_info"]
            if user_info:
                return user_info
            num += 1
        return None

    async def handle_template(self, requirement: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Process template-related requirements

        Args:
            requirement: User requirement description
            template: Template information

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

            # extrac user info
            user_info = await self.extract_user_info(requirement)
            logger.info(f"User info: {user_info}")

            return f"Successfully copied {template.style} template, next step is to rename the template folder to the project name", user_info

        except Exception as e:

            return f"Error during template processing: {str(e)}", None


# 测试
async def main():
    engineer = FrontendEngineer()
    result = await engineer.handle_template("帮我设计一个个人名片")
    if isinstance(result, tuple):
        template_result, user_info = result
        print(template_result)
        print(user_info)
    else:
        print(result)

if __name__ == "__main__":
    asyncio.run(main())