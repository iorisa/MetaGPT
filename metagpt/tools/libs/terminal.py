import asyncio
import os
import re
import time
from asyncio import Queue
from asyncio.subprocess import PIPE, STDOUT, Process
from pathlib import Path
from typing import Optional, Union

from metagpt.config2 import Config
from metagpt.const import DEFAULT_WORKSPACE_ROOT, SWE_SETUP_PATH
from metagpt.logs import logger
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.report import END_MARKER_VALUE, TerminalReporter

DETACH_PROMPT = """
The command is running in detach at tab {detached_tab_id}, currently with output: {output_so_far}
New tab info: {new_tab_info}
You may operate on the new tab, or switch back to the detached tab {detached_tab_id} and input command using switch_tab plus run_command
"""


@register_tool(include_functions=["run_command", "switch_tab"])
class Terminal:
    """
    A tool for running terminal commands.
    Don't initialize a new instance of this class if one already exists.
    For commands that need to be executed within a Conda environment, it is recommended
    to use the `execute_in_conda_env` method.
    """

    def __init__(self):
        self.shell_command = ["bash"]  # FIXME: should consider windows support later
        self.command_terminator = "\n"
        self.stdout_queue = Queue(maxsize=1000)
        self.observer = TerminalReporter()
        self.tabs: Optional[dict[str, Process]] = {}
        self.current_tab_id: str = ""
        self.process: Optional[Process] = None  # process of the current tab
        self.tab_stdout_queue: dict[str, Queue] = {}
        #  The cmd in forbidden_terminal_commands will be replace by pass ana return the advise. example:{"cmd":"forbidden_reason/advice"}
        self.forbidden_commands = {
            "run dev": "Use Deployer.deploy_to_public instead.",
            "run preview": "Use Deployer.deploy_to_public instead.",
            # serve cmd have a space behind it,
            "serve ": "Use Deployer.deploy_to_public instead.",
        }
        self.initial_workdir = None  # to be set by the agent using it

    async def _start_process(self):
        # Start a persistent shell process
        process = await asyncio.create_subprocess_exec(
            *self.shell_command,
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
            executable="bash",
            env=os.environ.copy(),
            cwd=DEFAULT_WORKSPACE_ROOT.absolute(),
        )
        return process

    def switch_tab(self, tab_id: str = "") -> str:
        if tab_id in self.tabs:
            self.process = self.tabs[tab_id]
            self.current_tab_id = tab_id
            tab_new_output = self._read_background_output()
            return f"Switched to tab {tab_id}, the tab has new output: {tab_new_output}"
        return f"Tab {tab_id} not found, created tabs are {list(self.tabs.keys())}"

    async def _create_new_tab(self) -> str:
        process = await self._start_process()
        tab_id = f"{len(self.tabs):02}"
        self.tabs = {tab_id: process}
        self.switch_tab(tab_id)
        self.current_tab_id = tab_id
        pwd = await self._check_state()
        return f"Tab {tab_id} created and switched to successfully, with pwd at {pwd}"

    async def _check_state(self):
        """
        Check the state of the terminal, e.g. the current directory of the terminal process. Useful for agent to understand.
        """
        output = await self.run_command("pwd")
        logger.info(f"The terminal is at: {output}")
        return output

    async def run_command(self, cmd: str, daemon=False) -> str:
        """
        Executes a specified command in the terminal and streams the output back in real time.
        This command maintains state across executions, such as the current directory,
        allowing for sequential commands to be contextually aware.

        Args:
            cmd (str): The command to execute in the terminal.
            daemon (bool): If True, executes the command in an asynchronous task, allowing
                           the main program to continue execution.
        Returns:
            str: The command's output or an empty string if `daemon` is True. Remember that
                 when `daemon` is True, use the `get_stdout_output` method to get the output.
        """
        if self.process is None:
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
        self.process.stdin.write((cmd + self.command_terminator).encode())
        self.process.stdin.write(
            f'echo "{END_MARKER_VALUE}"{self.command_terminator}'.encode()  # write EOF
        )  # Unique marker to signal command end
        await self.process.stdin.drain()
        if daemon:
            asyncio.create_task(self._read_and_process_output(cmd))
        else:
            output += await self._read_and_process_output(cmd)

        return output

    async def set_initial_workdir(self, path: Union[str, Path]):
        if Path(path).exists():
            await self.run_command(f"cd {path}")
            self.initial_workdir = path

    async def execute_in_conda_env(self, cmd: str, env, daemon=False) -> str:
        """
        Executes a given command within a specified Conda environment automatically without
        the need for manual activation. Users just need to provide the name of the Conda
        environment and the command to execute.

        Args:
            cmd (str): The command to execute within the Conda environment.
            env (str, optional): The name of the Conda environment to activate before executing the command.
                                 If not specified, the command will run in the current active environment.
            daemon (bool): If True, the command is run in an asynchronous task, similar to `run_command`,
                           affecting error logging and handling in the same manner.

        Returns:
            str: The command's output, or an empty string if `daemon` is True, with output processed
                 asynchronously in that case.

        Note:
            This function wraps `run_command`, prepending the necessary Conda activation commands
            to ensure the specified environment is active for the command's execution.
        """
        cmd = f"conda run -n {env} {cmd}"
        return await self.run_command(cmd, daemon=daemon)

    async def _read_background_output(self) -> str:
        """
        Retrieves all collected output from background running commands and returns it as a string.

        Returns:
            str: The collected output from background running commands, returned as a string.
        """
        tmp = []
        while True:
            new_output = b""
            try:
                # Set a timeout for the read operation
                new_output = await asyncio.wait_for(self.process.stdout.read(1), timeout=1)
                tmp.append(new_output)
            except asyncio.TimeoutError:
                print("No more data to read")
                break
        return b"".join(tmp).decode()

    async def _read_and_process_output(self, cmd: str, daemon: bool = False, timeout: int = 20) -> str:
        async with self.observer as observer:
            cmd_output = []
            await observer.async_report(cmd + self.command_terminator, "cmd")
            # report the command
            # Read the output until the unique marker is found.
            # We read bytes directly from stdout instead of text because when reading text,
            # '\r' is changed to '\n', resulting in excessive output.
            start_time = time.time()
            tmp = []
            while True:
                new_output = b""
                try:
                    # Set a timeout for the read operation
                    new_output = await asyncio.wait_for(self.process.stdout.read(1), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.info("No more output, detached from current tab and switched to a new tab")

                if not new_output:
                    if time.time() - start_time > timeout:
                        output_so_far = "".join(cmd_output) + b"".join(tmp).decode()
                        detached_tab_id = self.current_tab_id
                        new_tab_info = await self._create_new_tab()
                        instruction = DETACH_PROMPT.format(
                            detached_tab_id=detached_tab_id,
                            output_so_far=output_so_far,
                            new_tab_info=new_tab_info,
                        )
                        return instruction
                    else:
                        continue
                start_time = time.time()  # has output, reset start time

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
                            # report stdout in real-time
                            cmd_output.append(line)
                        return "".join(cmd_output)
                    # log stdout in real-time
                    await observer.async_report(line, "output")
                    # print(line)
                    cmd_output.append(line)
                    if daemon:
                        await self.stdout_queue.put(line)

    async def close(self):
        """Close the persistent shell process."""
        self.process.stdin.close()
        await self.process.wait()


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
        await self.run_command(f"cd {Config.default().workspace.path}")
        await self.run_command(f"source {SWE_SETUP_PATH}")

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

        return await self.run_command(cmd)
