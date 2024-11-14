import copy
import re
from pathlib import Path
from typing import Tuple

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
from metagpt.utils.common import any_to_str
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

        flag = await self._is_development_request(send_msg)
        # logger.info(f"think: {send_msg}, {flag}")
        if self.is_first_dev_request and flag:
            template_result = await self.handle_template(send_msg.content)
            logger.info(f"Template search result: {template_result}")
            self.is_first_dev_request = False  # Update flag

            # Update memory
            self.rc.memory.add(UserMessage(content=template_result))

        else:
            logger.warning("Current message is not a development request")

        await self._format_instruction()
        res = await super()._think()
        return res

    async def _is_development_request(self, send_msg: Message) -> bool:
        """判断当前请求是否为软件开发需求
        
        使用 LLM 来智能判断用户输入是否属于软件开发需求。

        Args:
            send_msg: 当前角色收到的消息
            
        Returns:
            bool: 是否为软件开发需求
        """
        try:
            # 使用 RoleZero 进行快速判断
            prompt = f"""请判断以下用户输入是否是一个web开发相关的需求(请不要回答其他内容, 名片设计类请求也属于web开发)：
            
            用户输入: {send_msg.content}
            
            只需要回答 "是" 或 "否"。"""
            
            result = await self.llm.aask(prompt)
            return result.strip() != "否"
            
        except Exception as e:
            logger.warning(f"Error in _is_development_request: {str(e)}")
            return False

    def _retrieve_experience(self) -> str:
        return FE_EXAPMLE

    async def set_template(self, template_info: TemplateInfo=None) -> None:
        if template_info is not None:
            """更新模板信息到系统提示词"""
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
            # 更新指令中的模板部分
            self.instruction = self.instruction.replace(
                GENERAL_WEB_APP_TEMPLATE,
                self._template_content
            )
            logger.info(f"Template update successfully")

    def _get_template_content(self, template: TemplateInfo) -> str:
        """获取模板文件内容"""
        content = ""
        try:
            for file_path in template.template_path.rglob("*"):
                if file_path.is_file() and file_path.suffix in ['.html', '.js', '.css']:
                    content += f"\n#### {file_path.name}\n"
                    content += read_file_by_path(file_path)
            return content
        except Exception:
            return ""

    async def handle_template(self, requirement: str) -> str:
        """Process template-related requirements

        Args:
            requirement: User requirement description

        Returns:
            Processing result description
        """
        try:
            # 1. 搜索匹配的模板
            template = await self.template_tool.search(requirement)
            if not template:
                return "未找到匹配的模板"

            # template, user_info = result

            # 2. 应用模板
            await self.set_template(template)

            success = await self.template_tool.copy_template(template)
            if not success:
                return "模板复制失败"


            return f"成功复制{template.style.value}模板，下一步请修改template文件夹名字为项目名字"

        except Exception as e:

            return f"模板处理过程中出现错误: {str(e)}"
