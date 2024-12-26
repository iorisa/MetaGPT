from __future__ import annotations

import asyncio
import re
from pathlib import Path

from pydantic import Field, model_validator

from metagpt.logs import logger
from metagpt.prompts.di.engineer2 import ENGINEER2_INSTRUCTION, WRITE_CODE_PROMPT
from metagpt.prompts.di.supabase import get_supabase_code_requirement
from metagpt.roles.di.role_zero import RoleZero
from metagpt.schema import UserMessage
from metagpt.strategy.experience_retriever import ENGINEER_EXAMPLE
from metagpt.tools.libs.cr import CodeReview
from metagpt.tools.libs.deployer import Deployer
from metagpt.tools.libs.editor import FileBlock
from metagpt.tools.libs.git import git_create_pull
from metagpt.tools.libs.image_getter import ImageGetter
from metagpt.tools.libs.supabase_manager import get_supabase_manager_instance
from metagpt.tools.libs.terminal import Terminal
from metagpt.tools.tool_recommend import BM25ToolRecommender, ToolRecommender
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.common import CodeParser, awrite, log_time
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
        "Deployer",
        "SupabaseManager",
        # "UserInfoParser",
    ]

    # SWE Agent parameter
    run_eval: bool = False
    output_diff: str = ""
    max_react_loop: int = 40

    # Code tools related attributes
    code_tools: list[str] = ["ImageGetter"]
    code_tool_execution_list: list[str] = ["ImageGetter.get", "ImageGetter.process"]
    code_tool_recommender: ToolRecommender = None

    async def _think(self) -> bool:
        await self._update_workdir()
        res = await super()._think()
        return res

    @model_validator(mode="after")
    def set_code_tool(self) -> "Engineer2":
        """Initialize code tool recommender if execution list exists."""
        if self.code_tool_execution_list and not self.code_tool_recommender:
            # Check if the code tools is available
            if ImageGetter.is_available():
                self.code_tool_recommender = BM25ToolRecommender(tools=self.code_tools, force=True)
        return self

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
        supabase_manager = get_supabase_manager_instance()

        tool_execution = {
            "git_create_pull": git_create_pull,
            "Engineer2.write_new_code": self.write_new_code,
            "CodeReview.review": cr.review,
            "CodeReview.fix": cr.fix,
            "Terminal.run_command": self.terminal.run_command,
            "Deployer.deploy_to_public": self._deploy_to_public,
            "SupabaseManager.execute_sql": supabase_manager.execute_sql,
            "SupabaseManager.get_session_schemas": supabase_manager.get_session_schemas,
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

    @log_time
    async def _tool_call(self, code: str):
        """Execute tool calls in code and replace with results."""
        # Check the tool whether available
        if not ImageGetter.is_available():
            return code

        # Regex pattern to match tool call tags like <tool_call.../>
        # Uses [\s\S] for multi-line matching and non-greedy *? to avoid over-matching
        # Supports optional $ prefix: $<tool_call.../>
        tool_call_pattern = r"(?:\$)?<tool_call>[\s\S]*?[\s\S]</tool_call>"
        tool_calls = re.findall(tool_call_pattern, code)

        async def execute_tool(tool_call: str):
            # Extract just the function call part
            tool_name_str = r"|".join(self.code_tool_execution_list)
            func_match = re.search(rf"({tool_name_str})\(.*?\)", tool_call)
            if not func_match:
                return None

            func_call = func_match.group(0)

            # Create namespace with available tools
            namespace = {"ImageGetter": ImageGetter()}

            # Execute the function call
            result = await eval(func_call, {"__builtins__": {}}, namespace)
            return tool_call, result

        # Process all tool calls concurrently
        results = await asyncio.gather(*[execute_tool(tc) for tc in tool_calls])

        # Replace tool calls with results
        replaced = []
        for result in results:
            if result:
                tool_call, replacement = result
                code = code.replace(tool_call, replacement)
                replaced.append((tool_call, replacement))

        return code, replaced

    async def write_new_code(self, description: str, paths: list[str]) -> str:
        """Write one or more new code files.

        Args:
            description (str): "Brief description and important notes of what and how to implement the files, including how they interact with each other if there will be multiple files.
            paths (list[str]): The paths of the files to be created.
        """
        # Get recommended code tools and their usage examples.
        if self.code_tool_recommender:
            code_tool_info = await self.code_tool_recommender.get_recommended_tool_info()
        else:
            code_tool_info = "N/A"
        prompt = WRITE_CODE_PROMPT.format(
            file_path=paths,
            file_description=description,
            available_code_tools=code_tool_info,
            supabase_code_requirement=get_supabase_code_requirement(),
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
            all_replaced_snippets = []
            for path, code in zip(paths, code_by_files):
                code, replaced_snippets = await self._tool_call(code)
                await awrite(self._fix_path(path), code)
                file_block = FileBlock(path=str(path), content=code)
                output_msg = f"{output_msg}File created successfully with \n{file_block}\n"
                if len(replaced_snippets) > 0:
                    all_replaced_snippets.extend(replaced_snippets)
            if all_replaced_snippets:
                replaced_msg = "The following tool calls have been replaced with the call results:\n"
                replaced_msg += "\n".join([f"Replaced {old} with {new}" for old, new in all_replaced_snippets])
                # Add the content that the system automatically replaces and the fact that the tool call was executed automatically to memory.
                self.rc.memory.add(UserMessage(content=replaced_msg))

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
