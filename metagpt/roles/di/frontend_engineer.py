import os
import subprocess

# from agentops import track_agent
from pydantic import model_validator

from metagpt.logs import logger
from metagpt.prompts.di.frontend_engineer import FE_EXAPMLE, FRONTEND_ENGINEER_PROMPT
from metagpt.prompts.di.template import GENERAL_WEB_APP_TEMPLATE_PROMPT
from metagpt.roles.di.engineer2 import Engineer2
from metagpt.schema import UserMessage
from metagpt.tools.libs.search_template import SearchTemplate, TemplateInfo


# @track_agent("FrontendEngineer")
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
        "Browser",
    ]
    is_first_dev_request: bool = True

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

    async def set_template(
        self, template_info: TemplateInfo = None, extra_user_info: str = None, extra_info: str = None
    ) -> None:
        self._template_content = await self.template_tool.get_template_info(template_info)
        # Update template part in instruction
        self.instruction = self.instruction.replace(GENERAL_WEB_APP_TEMPLATE_PROMPT, self._template_content)

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

            extra_info = f"""
                1.Successfully copied the {template.style} template to the {target_dir} directory. 
                2.The project root directory is {target_dir}, you need to go into the project root directory: {target_dir} firstly. 
                3.And if the project root directory exists README.md document, read README.md document firstly. 
                4.If user does not provide additional information, you need to deploy the project directly without updating any code. However, if the user specifies obtaining their information from a certain website or file, use the appropriate tools to retrieve it, and then update the obtained information into the project. 
                # Note
                1.If the code file that needs to be updated already exists, do not rewrite the corresponding content, but replace some of the code to update. 
                2.Before updating the code at the project path, read the content of the code file and then think about how to update it at the project path. 
                3.If the project does not belong to React or Vue projects, then do not run the project code.
                # CRUCIAL
                1.Code updates should be done in the project root directory:{target_dir}, so you should use ```cd {target_dir}``` to go into the project root directory firstly, and then use editor to write code. This step is CRUCIAL for the project to be developed correctly.
                2.When using the editor to write code, plan the code files to use absolute paths as much as possible to reduce path errors.
            """
            await self.set_template(template, extra_user_info, extra_info)

            return target_dir
        else:
            return ""
