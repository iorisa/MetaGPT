#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/5/25
@Author  : mashenquan
@File    : requirement_implement.py
"""
import asyncio
import json
from pathlib import Path
from typing import Any, Dict

import typer
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions import WriteDesign
from metagpt.config2 import Config
from metagpt.const import DEFAULT_WORKSPACE_ROOT
from metagpt.context import Context
from metagpt.environment import Environment
from metagpt.logs import logger
from metagpt.roles import Engineer, ProjectManager
from metagpt.schema import Message
from metagpt.utils.common import CodeParser, aread, general_after_log
from metagpt.utils.file_repository import FileRepository
from metagpt.utils.git_repository import GitRepository
from metagpt.utils.project_repo import ProjectRepo

app = typer.Typer(add_completion=False)


class EnvBuilder(BaseModel):
    context: Context
    filename: str
    language: str
    platform: str

    async def _load_system_design(self) -> str:
        design = await aread(filename=self.filename)
        m = json.loads(design)
        file_list = m.get("File list", [])
        if not file_list:
            raise ValueError("Invalid system design file, `File list` does not exists.")
        if m["Language"].lower() != self.language.lower():
            m = await self._switch_language(design=m)
        if self.platform:
            m["Runtime Platform Constraints"] = self.platform
        design = json.dumps(m)
        return design

    async def build(self) -> Environment:
        design = await self._load_system_design()
        self.context.git_repo = GitRepository(local_path=DEFAULT_WORKSPACE_ROOT / FileRepository.new_filename())
        self.context.repo = ProjectRepo(self.context.git_repo)
        await self.context.repo.docs.system_design.save(
            filename=FileRepository.new_filename() + ".json", content=design
        )

        env = Environment(context=self.context)
        return env

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _switch_language(self, design: Dict[str, Any]) -> Dict[str, Any]:
        prompt = "## Source File List\n" + "".join([f"- {i}\n" for i in design["File list"]])
        llm = self.context.llm_with_cost_manager_from_llm_config(self.context.config.llm)
        rsp = await llm.aask(
            msg=prompt,
            system_msgs=[
                f'Modify the file extensions of "Source File List" to match the coding language "{self.language}".',
                "Return the modified markdown JSON object with:\n"
                '- a "files" key contains the string list of modified filenames of "Source File List" section;\n'
                '- a "reason" key explaining why.\n',
            ],
        )
        json_block = CodeParser.parse_code(text=rsp, lang="json", block="")
        v = json.loads(json_block)
        design.update({"File list": v["files"], "Language": self.language})
        return design


async def develop(context: Context, system_design_filename: str, language: str, platform: str):
    env = await EnvBuilder(
        context=context, filename=system_design_filename, language=language, platform=platform
    ).build()
    env.add_roles([ProjectManager(), Engineer(n_borg=5, use_code_review=True)])
    env.publish_message(Message(content="", cause_by=WriteDesign, send_to="Eve"))
    while not env.is_idle:
        await env.run()
    context.git_repo.archive()


@app.command()
def startup(
    filename: str = typer.Argument(..., help="The filename of system design written by `requirement_analyze.py`."),
    language: str = typer.Option(
        default="python", help="Which language should be used to write the code. The default language is python."
    ),
    llm_config: str = typer.Option(default="", help="Low-cost LLM config"),
    platform: str = typer.Option(default="Ding Talk Android App", help="What platform these codes will run on."),
):
    if llm_config and Path(llm_config).exists():
        config = Config.from_yaml_file(Path(llm_config))
    else:
        logger.info("GPT 4 turbo is recommended")
        config = Config.default()
    ctx = Context(config=config)
    asyncio.run(develop(ctx, filename, language, platform))


if __name__ == "__main__":
    app()
