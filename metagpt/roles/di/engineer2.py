from __future__ import annotations

from pathlib import Path

# from agentops import track_agent
from pydantic import Field

from metagpt.logs import logger

# from metagpt.actions.write_code_review import ValidateAndRewriteCode
from metagpt.prompts.di.engineer2 import ENGINEER2_INSTRUCTION, WRITE_CODE_PROMPT
from metagpt.roles.di.role_zero import RoleZero
from metagpt.schema import UserMessage
from metagpt.strategy.experience_retriever import ENGINEER_EXAMPLE
from metagpt.tools.libs.cr import CodeReview
from metagpt.tools.libs.deployer import Deployer
from metagpt.tools.libs.editor import FileBlock
from metagpt.tools.libs.git import git_create_pull
from metagpt.tools.libs.image_getter import ImageGetter
from metagpt.tools.libs.supabase_manager import SupabaseManager
from metagpt.tools.libs.terminal import Terminal
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.common import CodeParser, awrite
from metagpt.utils.report import EditorReporter


# @track_agent("Engineer2")
@register_tool(include_functions=["write_new_code"])
class Engineer2(RoleZero):
    name: str = "Alex"
    profile: str = "Engineer"
    goal: str = "Take on game, app, web development and deployment."
    instruction: str = ENGINEER2_INSTRUCTION
    terminal: Terminal = Field(default_factory=Terminal, exclude=True)
    deployer: Deployer = Field(default_factory=Deployer, exclude=True)
    tools: list[str] = [
        "Plan",
        "Editor",
        "RoleZero",
        "Terminal:run_command",
        "Browser:goto,scroll",
        "git_create_pull",
        "SearchEnhancedQA",
        "Engineer2",
        "CodeReview",
        "ImageGetter",
        "Deployer",
        "SupabaseManager",
    ]
    # SWE Agent parameter
    run_eval: bool = False
    output_diff: str = ""
    max_react_loop: int = 40
    # Add a tag to track whether this is the first time receiving software development requirements.
    is_first_dev_request: bool = Field(default=True, exclude=False)

    async def _think(self) -> bool:
        await self._update_workdir()
        res = await super()._think()
        return res

    async def _update_workdir(self):
        """
        Display the current terminal and editor state.
        This information will be dynamically added to the command prompt.
        """
        if not self.terminal.initial_workdir:
            # A special case to set terminal dir based on Role dir. This happens one time when Role is deserialized and terminal re-initialized
            await self.terminal.set_initial_workdir(self.working_dir)
        self.working_dir = (await self.terminal.run_command("pwd")).strip()
        self.editor.set_workdir(self.working_dir)

    def _update_tool_execution(self):
        cr = CodeReview()
        image_getter = ImageGetter()
        supabase_manager = SupabaseManager()

        tool_execution = {
            "git_create_pull": git_create_pull,
            "Engineer2.write_new_code": self.write_new_code,
            "ImageGetter.get_image": image_getter.get_image,
            "CodeReview.review": cr.review,
            "CodeReview.fix": cr.fix,
            "Terminal.run_command": self.terminal.run_command,
            "Deployer.deploy_to_public": self._deploy_to_public,
            "SupabaseManager.execute_sql": supabase_manager.execute_sql,
            "SupabaseManager.get_session_schemas": supabase_manager.get_session_schemas,
            "SupabaseManager.get_config": supabase_manager.get_config,
        }

        # Add additional tools only in evaluation mode
        if self.run_eval:
            tool_execution.update(
                {
                    "RoleZero.ask_human": self._end,
                    "RoleZero.reply_to_human": self._end,
                    "Terminal.run_command": self._eval_terminal_run,  # Override terminal command in eval mode
                }
            )

        self.tool_execution_map.update(tool_execution)

    def _retrieve_experience(self) -> str:
        return ENGINEER_EXAMPLE

    def _fix_path(self, path: str) -> Path:
        """Tries to fix the path if it is not absolute."""
        if not isinstance(path, Path):
            path = Path(path)
        if not path.is_absolute():
            path = self.working_dir / path
        return path

    async def write_new_code(self, description: str, paths: list[str]) -> str:
        """Write one or more new code files.

        Args:
            description (str): "Brief description and important notes of what and how to implement the files, including how they interact with each other if there will be multiple files.
            path (list[str]): The paths of the files to be created.
        """
        prompt = WRITE_CODE_PROMPT.format(
            file_path=paths,
            file_description=description,
        )
        # Sometimes the Engineer repeats the last command to respond.
        # Replace the last command with a manual prompt to guide the Engineer to write new code.
        memory = self.rc.memory.get(self.memory_k)[:-1]
        context = self.llm.format_msg(memory + [UserMessage(content=prompt)])

        async with EditorReporter(enable_llm_stream=True) as reporter:
            await reporter.async_report({"type": "files", "paths": [str(self._fix_path(i)) for i in paths]}, "meta")
            rsp = await self.llm.aask(context, system_msgs=[self.instruction])
            code_by_files = CodeParser.parse_multiple_code(text=rsp)

            output_msg = ""
            if len(paths) != len(code_by_files):
                logger.warning("The number of paths and code blocks do not match.")
                output_msg += f"The number of paths and code blocks do not match. Only {paths[:len(code_by_files)]} will be saved. If you want to save more code blocks, please call the function again with the remaining paths.\n"
            for path, code in zip(paths, code_by_files):
                await awrite(self._fix_path(path), code)
                file_block = FileBlock(path=str(path), content=code)
                output_msg += f"File created successfully with \n{file_block}\n"

        return output_msg

    async def _deploy_to_public(self, dist_dir, proj_name):
        """fix the dist_dir path to absolute path before deploying
        Args:
            dist_dir (str): The dist directory of the web project after run build. This must be an absolute path.
        """
        # Try to fix the path with the editor's working directory.
        if not Path(dist_dir).is_absolute():
            default_dir = self._fix_path(dist_dir)
            if not default_dir.exists():
                raise ValueError("dist_dir must be an absolute path.")
            dist_dir = default_dir
        return await self.deployer.deploy_to_public(dist_dir, proj_name)

    async def _eval_terminal_run(self, cmd):
        """change command pull/push/commit to end."""
        if any([cmd_key_word in cmd for cmd_key_word in ["pull", "push", "commit"]]):
            # The Engineer2 attempts to submit the repository after fixing the bug, thereby reaching the end of the fixing process.
            logger.info("Engineer2 use cmd:{cmd}\nCurrent test case is finished.")
            # Set self.rc.todo to None to stop the engineer.
            self._set_state(-1)
        else:
            command_output = await self.terminal.run_command(cmd)
        return command_output

    async def _end(self):
        if not self.planner.plan.is_plan_finished():
            self.planner.plan.finish_all_tasks()
        return await super()._end()
