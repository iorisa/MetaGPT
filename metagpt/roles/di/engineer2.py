from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, Tuple

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
        "Deployer",
    ]
    # SWE Agent parameter
    run_eval: bool = False
    output_diff: str = ""
    max_react_loop: int = 40
    # Add a tag to track whether this is the first time receiving software development requirements.
    autocall_tool_execution_map: dict = {}

    async def _think(self) -> bool:
        await self._format_instruction()

        rsp = await super()._think()
        return rsp

    async def _format_instruction(self):
        """
        Display the current terminal and editor state.
        This information will be dynamically added to the command prompt.
        """
        if not self.terminal.initial_workdir:
            # A special case to set terminal dir based on Role dir. This happens one time when Role is deserialized and terminal re-initialized
            await self.terminal.set_initial_workdir(self.working_dir)
        self.working_dir = (await self.terminal.run_command("pwd")).strip()
        self.editor.set_workdir(self.working_dir)
        self.cmd_prompt_current_state = f"current directory: {self.working_dir}"

    def _update_tool_execution(self):
        # validate = ValidateAndRewriteCode()
        cr = CodeReview()
        image_getter = ImageGetter()
        self.autocall_tool_execution_map.update(
            {
                "ImageGetter.get_image": image_getter.get_image,
                "ImageGetter.create_image": image_getter.create_image,
            }
        )
        if self.run_eval is True:
            # Evalute tool map
            self.tool_execution_map.update(
                {
                    "git_create_pull": git_create_pull,
                    "Engineer2.write_new_code": self.write_new_code,
                    "CodeReview.review": cr.review,
                    "CodeReview.fix": cr.fix,
                    "Terminal.run_command": self._eval_terminal_run,
                    "RoleZero.ask_human": self._end,
                    "RoleZero.reply_to_human": self._end,
                    "Deployer.deploy_to_public": self._deploy_to_public,
                }
            )
        else:
            # Default tool map
            self.tool_execution_map.update(
                {
                    "git_create_pull": git_create_pull,
                    "Engineer2.write_new_code": self.write_new_code,
                    "CodeReview.review": cr.review,
                    "CodeReview.fix": cr.fix,
                    "Terminal.run_command": self.terminal.run_command,
                    "Deployer.deploy_to_public": self._deploy_to_public,
                }
            )

    def _retrieve_experience(self) -> str:
        return ENGINEER_EXAMPLE

    def _fix_path(self, path: str) -> Path:
        """Tries to fix the path if it is not absolute."""
        if not isinstance(path, Path):
            path = Path(path)
        if not path.is_absolute():
            path = self.working_dir / path
        return path

    def parse_tool_call(self, tool_call: str) -> Tuple[str, Dict[str, Any]]:
        """Parse a tool call string into function name and parameters using eval."""

        class CallCatcher:
            def __getattr__(self, name):
                def _method(*args, **kwargs):
                    _method.args = args
                    _method.kwargs = kwargs
                    return _method

                _method.name = name
                return _method

        namespace = {"ImageGetter": CallCatcher()}

        try:
            mock_method = eval(tool_call, {"__builtins__": {}}, namespace)

            if not hasattr(mock_method, "name"):
                raise ValueError("Tool call was not captured correctly.")

            func_name = f"{tool_call.split('.')[0]}.{mock_method.name}"

            params = {f"arg{i}": arg for i, arg in enumerate(mock_method.args)}
            params.update(mock_method.kwargs)

            return func_name, params

        except Exception as e:
            raise ValueError(f"Invalid tool call format: {e}")

    async def _run_auto_tool_call_commands(self, tool_call_commands: list[dict[str, str]]):
        """Run the tool call commands concurrently."""
        coroutines = [
            self.autocall_tool_execution_map[cmd["command_name"]](**cmd["parameters"]) for cmd in tool_call_commands
        ]
        return await asyncio.gather(*coroutines)

    async def _tool_call(self, code: str):
        """Replace the tool call with the actual tool call."""
        replaced = []

        # Find all tool calls using regex
        tool_call_pattern = r"(?:\$)?\{<tool_call[\s\S]*?[\s\S]/>(?:\})?"
        for tool_call in re.findall(tool_call_pattern, code):
            # Extract the detail tool call function string with regex
            auto_tool_func_name_pattern = "|".join([tool_name for tool_name in self.autocall_tool_execution_map.keys()])
            tool_call_func = re.search(rf"({auto_tool_func_name_pattern})\(.*?\)", tool_call).group(0)

            try:
                # Parse the tool call
                func_name, params = self.parse_tool_call(tool_call_func)

                # Execute the tool
                result = await self.autocall_tool_execution_map[func_name](**params)

                # Replace in the code
                code = code.replace(tool_call, result)
                replaced.append((tool_call, result))

            except ValueError as e:
                logger.warning(f"Failed to parse tool call '{tool_call_func}': {e}")
                continue

        return code, replaced

    async def write_new_code(self, description: str, paths: list[str]) -> str:
        """Write one or more new code files.

        Args:
            description (str): "Brief description and important notes of what and how to implement the files, including how they interact with each other if there will be multiple files.
            paths (list[str]): The paths of the files to be created.
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
                output_msg += f"The number of paths and code blocks do not match. Only {paths} will be saved. If you want to save more code blocks, please call the function again with the remaining paths.\n"
            all_replaced_snipes = []
            for path, code in zip(paths, code_by_files):
                code, replaced_snipes = await self._tool_call(code)
                await awrite(self._fix_path(path), code)
                file_block = FileBlock(path=str(path), content=code)
                output_msg = f"{output_msg}File created successfully with \n{file_block}\n"
                if len(replaced_snipes) > 0:
                    all_replaced_snipes.extend(replaced_snipes)
            if all_replaced_snipes:
                replaced_msg = "The following tool calls have been replaced with the actual tool calls:\n"
                replaced_msg += "\n".join([f"Replaced {old} with {new}" for old, new in all_replaced_snipes])
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
