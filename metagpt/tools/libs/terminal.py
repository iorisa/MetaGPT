import asyncio
import os
import re
from asyncio.subprocess import PIPE, STDOUT, Process
from typing import Optional

import psutil
from pydantic import BaseModel, ConfigDict, Field, model_validator

from metagpt.config2 import Config
from metagpt.const import DEFAULT_WORKSPACE_ROOT, SWE_SETUP_PATH
from metagpt.logs import logger
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.report import END_MARKER_VALUE, TerminalReporter

DETACH_PROMPT = """
The command is running in detach at tab {detached_tab_id}, currently with output: {output_so_far}
New tab info: [{new_tab_info}]
Note: You may operate on the new tab, or switch back to the detached tab {detached_tab_id} to get incremental output. If you successfully launch a service at the detached tab {detached_tab_id}, you can also preview it (tab_id: {detached_tab_id}).
"""


def is_service_process(output: str) -> bool:
    pattern = r"localhost:\d+|[\d.]+:\d+"  # match localhost:port or ip:port"
    return bool(re.search(pattern, output))


class Tab(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tab_id: str = "temp_id"
    process: Process = Field(default=None, exclude=True)
    cwd: str = Field(default_factory=lambda: str(DEFAULT_WORKSPACE_ROOT.absolute()))
    observer: TerminalReporter = Field(default_factory=TerminalReporter)
    shell_command: list[str] = ["bash"]  # FIXME: should consider windows support later
    command_terminator: str = "\n"
    output_queue: asyncio.Queue = Field(default_factory=asyncio.Queue, exclude=True)
    task: Optional[asyncio.Task] = Field(None, exclude=True)

    async def _start_process(self):
        # Start a persistent shell process
        self.process = await asyncio.create_subprocess_exec(
            *self.shell_command,
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
            executable="bash",
            env=os.environ.copy(),
            cwd=self.cwd,
        )

    async def start(self):
        if not self.process:
            await self._start_process()

    def read(self, *args, **kwargs):
        return self.process.stdout.read(*args, **kwargs)

    def write(self, *args, **kwargs):
        return self.process.stdin.write(*args, **kwargs)

    async def close(self):
        """Close the persistent shell process."""
        self.process.stdin.close()
        await self.process.wait()

    async def execute(self, cmd: str) -> asyncio.Task:
        """
        Executes a specified command in the terminal and streams the output back in real time.

        Args:
            cmd (str): The command to execute in the terminal.

        Returns:
            str: The command's output.
        """
        if not self.process or self.process.returncode is not None:
            await self._start_process()

        self.write((cmd + self.command_terminator).encode())
        self.write(
            f'echo "{END_MARKER_VALUE}"{self.command_terminator}'.encode()  # write EOF
        )  # Unique marker to signal command end
        await self.process.stdin.drain()

        self.task = asyncio.create_task(self.read_and_process_output(cmd))
        return self.task

    async def read_and_process_output(self, cmd: str) -> str:
        output_queue = self.output_queue
        process = self.process
        async with self.observer as observer:
            cmd_output = []
            await observer.async_report(cmd + self.command_terminator, "cmd")
            # report the command
            # Read the output until the unique marker is found.
            # We read bytes directly from stdout instead of text because when reading text,
            # '\r' is changed to '\n', resulting in excessive output.
            tmp = []
            while process.returncode is None:
                new_output = await self.read(1)
                tmp.append(new_output)
                if new_output == b"\n":
                    # each time gather a full line, record and report it, and reset the tmp holder
                    line = b"".join(tmp).decode()
                    tmp = []
                    ix = line.rfind(END_MARKER_VALUE)
                    if ix >= 0:
                        line = line[0:ix]
                        if line:
                            await observer.async_report(line, "output")
                            await output_queue.put(line)
                            # report stdout in real-time
                            cmd_output.append(line)
                        await output_queue.put(None)
                        self.update_cwd()  # update cwd if command executed
                        return "".join(cmd_output)
                    # log stdout in real-time
                    await observer.async_report(line, "output")
                    await output_queue.put(line)
                    cmd_output.append(line)

    def read_background_output(self) -> str:
        """
        Retrieves all collected output from background running commands and returns it as a string.

        Returns:
            str: The collected output from background running commands, returned as a string.
        """
        tmp = []
        output_queue = self.output_queue
        while not output_queue.empty():
            line = output_queue.get_nowait()
            if line is None:
                break
            tmp.append(line)
        return "".join(tmp)

    @property
    def is_running(self):
        if self.task is None:
            return False
        if self.process.returncode is not None:
            return False
        return not self.task.done()

    def update_cwd(self):
        self.cwd = psutil.Process(self.process.pid).cwd()

    async def preview(self, port: str, proj_name: str) -> str:
        """Preview the service on this tab. To be implemented by users."""
        return f"{proj_name} service can now be viewed at http://127.0.0.1.nip.io:{port}"


@register_tool(include_functions=["run", "preview"])
class Terminal(BaseModel):
    """A tool for running terminal commands. Don't initialize a new instance of this class if one already exists."""

    tabs: dict[str, Tab] = {}
    current_tab_id: str = ""
    current_tab: Optional[Tab] = Field(None, exclude=True)
    #  The cmd in forbidden_terminal_commands will be replace by pass ana return the advise. example:{"cmd":"forbidden_reason/advice"}
    forbidden_commands: dict[str, str] = {
        # "run dev": "Use Deployer.deploy_to_public instead.",
        "run preview": "Use Deployer.deploy_to_public instead.",
        # serve cmd have a space behind it,
        "serve ": "Use Deployer.deploy_to_public instead.",
    }
    timeout: float = 20.0  # timeout for reading output

    @model_validator(mode="after")
    def valid_current_tab(self):
        if self.current_tab_id:
            self.current_tab = self.tabs[self.current_tab_id]
        return self

    async def switch_tab(self, tab_id: str = "") -> str:
        """Switch tab based on tab_id. Useful for checking out new output from detached tabs or typing on desired tabs."""
        # NOTE: Hide from agent for now (not registered), need to solve the echo END_MARKER_VALUE problem
        if tab_id in self.tabs:
            self.current_tab = self.tabs[tab_id]
            self.current_tab_id = tab_id
            tab_new_output = self.current_tab.read_background_output()
            return f"Switched to tab {tab_id}, pwd is {self.current_tab.cwd}, the tab has new output: {tab_new_output}"
        return f"Tab {tab_id} not found, created tabs are {list(self.tabs.keys())}"

    async def _create_new_tab(self) -> str:
        """create a new tab and switch to it"""
        new_tab_id = f"{len(self.tabs):02}"
        new_tab = Tab(tab_id=new_tab_id, cwd=self.cwd)
        await new_tab.start()
        self.tabs.update({new_tab_id: new_tab})
        switch_tab_info = await self.switch_tab(new_tab_id)
        return f"Tab {new_tab_id} created. " + switch_tab_info

    @property
    def cwd(self):
        return self.current_tab.cwd if self.current_tab else str(DEFAULT_WORKSPACE_ROOT.absolute())

    async def run(self, cmd: str) -> str:
        """
        Executes a specified command in the terminal and streams the output back in real time.

        Args:
            cmd (str): The command to execute in the terminal.

        Returns:
            str: The command's output.
        """
        if not self.current_tab:
            await self._create_new_tab()

        output = ""
        # Remove forbidden commands
        commands = re.split(r"\s*&&\s*", cmd)
        for cmd_name, reason in self.forbidden_commands.items():
            # "true" is a pass command in linux terminal.
            for index, command in enumerate(commands):
                if cmd_name in command:
                    output += f"Failed to execut {command}. {reason}\n"
                    commands[index] = "true"
        cmd = " && ".join(commands)

        # Send the command
        current_tab = self.current_tab
        if current_tab.is_running:
            return (
                "Cannot execute the command because a previous one is still running in the current terminal tab"
                f" (ID: {self.current_tab_id})."
            )

        # clear the output queue before execute command
        output_queue = current_tab.output_queue
        while not output_queue.empty():
            output_queue.get_nowait()

        await current_tab.execute(cmd)

        tmp = []
        is_service_flag = False
        while True:
            try:
                # shorter timeout for service process by detecting output patterns such as localhost:port, ip:port
                timeout = self.timeout if not is_service_flag else 3
                line = await asyncio.wait_for(output_queue.get(), timeout=timeout)
                if line is None:
                    break
                is_service_flag = is_service_flag or is_service_process(line)  # if True already, skip checking
                tmp.append(line)
            except asyncio.TimeoutError:
                output_so_far = "".join(tmp)
                if (returncode := current_tab.process.returncode) is not None:
                    msg = f"The terminal has exited with code {returncode}"
                    logger.warning(msg)
                    return f"{msg}, currently with output: {output_so_far}"

                current_tab.update_cwd()  # update cwd for the command still running
                logger.info(f"No more output after {timeout}s, detached from current tab and switched to a new tab")

                detached_tab_id = self.current_tab_id
                new_tab_info = await self._create_new_tab()
                instruction = DETACH_PROMPT.format(
                    detached_tab_id=detached_tab_id,
                    output_so_far=output_so_far,
                    new_tab_info=new_tab_info,
                )
                # print(instruction)
                return instruction
        return "".join(tmp)

    async def preview(self, tab_id: str, port: int, proj_name: str) -> str:
        """Preview a web project by forwarding a local port to public. Specify the id of the tab that runs the service, which is usually not the current tab but some detached tab."""
        if tab_id not in self.tabs:
            return f"Tab {tab_id} not found, created tabs are {list(self.tabs.keys())}, specify the correct tab_id that runs the service."
        return await self.tabs[tab_id].preview(port, proj_name)

    async def execute_in_conda_env(self, cmd: str, env) -> str:
        """
        Executes a given command within a specified Conda environment automatically without
        the need for manual activation. Users just need to provide the name of the Conda
        environment and the command to execute.

        Args:
            cmd (str): The command to execute within the Conda environment.
            env (str, optional): The name of the Conda environment to activate before executing the command.
                                 If not specified, the command will run in the current active environment.

        Returns:
            str: The command's output, or an empty string if `daemon` is True, with output processed
                 asynchronously in that case.

        Note:
            This function wraps `run`, prepending the necessary Conda activation commands
            to ensure the specified environment is active for the command's execution.
        """
        cmd = f"conda run -n {env} {cmd}"
        return await self.run(cmd)

    async def close(self):
        for tab in self.tabs.values():
            await tab.close()


@register_tool(include_functions=["run"])
class Bash(Terminal):
    """
    A class to run bash commands directly and provides custom shell functions.
    All custom functions in this class can ONLY be called via the `Bash.run` method.
    """

    def __init__(self):
        """init"""
        os.environ["SWE_CMD_WORK_DIR"] = str(Config.default().workspace.path)
        super().__init__()
        self.start_flag = False

    async def start(self):
        await super().run(f"cd {Config.default().workspace.path}")
        await super().run(f"source {SWE_SETUP_PATH}")

    async def run(self, cmd) -> str:
        """
        Executes a bash command.

        Args:
            cmd (str): The bash command to execute.

        Returns:
            str: The output of the command.

        This method allows for executing standard bash commands as well as
        utilizing several custom shell functions defined in the environment.

        Custom Shell Functions:

        - open <path> [<line_number>]
          Opens the file at the given path in the editor. If line_number is provided,
          the window will move to include that line.
          Arguments:
              path (str): The path to the file to open.
              line_number (int, optional): The line number to move the window to.
              If not provided, the window will start at the top of the file.

        - goto <line_number>
          Moves the window to show <line_number>.
          Arguments:
              line_number (int): The line number to move the window to.

        - scroll_down
          Moves the window down {WINDOW} lines.

        - scroll_up
          Moves the window up {WINDOW} lines.

        - create <filename>
          Creates and opens a new file with the given name.
          Arguments:
              filename (str): The name of the file to create.

        - search_dir_and_preview <search_term> [<dir>]
          Searches for search_term in all files in dir and gives their code preview
          with line numbers. If dir is not provided, searches in the current directory.
          Arguments:
              search_term (str): The term to search for.
              dir (str, optional): The directory to search in. Defaults to the current directory.

        - search_file <search_term> [<file>]
          Searches for search_term in file. If file is not provided, searches in the current open file.
          Arguments:
              search_term (str): The term to search for.
              file (str, optional): The file to search in. Defaults to the current open file.

        - find_file <file_name> [<dir>]
          Finds all files with the given name in dir. If dir is not provided, searches in the current directory.
          Arguments:
              file_name (str): The name of the file to search for.
              dir (str, optional): The directory to search in. Defaults to the current directory.

        - edit <start_line>:<end_line> <<EOF
          <replacement_text>
          EOF
          Line numbers start from 1. Replaces lines <start_line> through <end_line> (inclusive) with the given text in the open file.
          The replacement text is terminated by a line with only EOF on it. All of the <replacement text> will be entered, so make
          sure your indentation is formatted properly. Python files will be checked for syntax errors after the edit. If the system
          detects a syntax error, the edit will not be executed. Simply try to edit the file again, but make sure to read the error
          message and modify the edit command you issue accordingly. Issuing the same command a second time will just lead to the same
          error message again. All code modifications made via the 'edit' command must strictly follow the PEP8 standard.
          Arguments:
              start_line (int): The line number to start the edit at, starting from 1.
              end_line (int): The line number to end the edit at (inclusive), starting from 1.
              replacement_text (str): The text to replace the current selection with, must conform to PEP8 standards.

        - submit
          Submits your current code locally. it can only be executed once, the last action before the `end`.

        Note: Make sure to use these functions as per their defined arguments and behaviors.
        """
        if not self.start_flag:
            await self.start()
            self.start_flag = True

        return await super().run(cmd)
