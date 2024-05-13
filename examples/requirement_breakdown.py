#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : requirement_breakdown.py
@Desc    : The implementation of RFC225. https://deepwisdom.feishu.cn/wiki/VRq8wumeKiPcvIk9wcacwoIHnzc
"""
import asyncio
from pathlib import Path

import typer

from metagpt.actions import UserRequirement
from metagpt.actions.prepare_documents import PrepareDocuments
from metagpt.actions.requirement_analysis.analysis_report import WriteReport
from metagpt.actions.requirement_analysis.breakdown import (
    BreakdownRequirementSpecifications,
    ClassifyUseCase,
    IdentifyUseCase,
)
from metagpt.actions.requirement_analysis.breakdown.patch_use_case import PatchUseCase
from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.config2 import Config
from metagpt.configs.llm_config import LLMConfig
from metagpt.context import Context
from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.schema import Message
from metagpt.utils.common import any_to_str, aread

app = typer.Typer(add_completion=False)


class RequirementBreakdowner(Role):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Set events or actions the Architect should watch or be aware of
        self._watch(
            {
                UserRequirement,
                PrepareDocuments,
                BreakdownRequirementSpecifications,
                IdentifyUseCase,
                ClassifyUseCase,
                PatchUseCase,
            },
        )

    async def _observe(self, ignore_memory=False) -> int:
        return await super()._observe(ignore_memory=True)

    async def _think(self) -> bool:
        handlers = {
            any_to_str(UserRequirement): PrepareDocuments(context=self.context),
            any_to_str(PrepareDocuments): BreakdownRequirementSpecifications(context=self.context),
            any_to_str(BreakdownRequirementSpecifications): IdentifyUseCase(context=self.context),
            any_to_str(IdentifyUseCase): ClassifyUseCase(context=self.context),
            any_to_str(ClassifyUseCase): PatchUseCase(context=self.context),
            any_to_str(PatchUseCase): WriteReport(context=self.context),
        }
        self.rc.todo = handlers.get(self.rc.news[0].cause_by, None)
        return bool(self.rc.todo is not None)


async def breakdown(ctx: Context, requirement_filename: str):
    requirement = await aread(filename=requirement_filename, encoding="utf-8")
    msg = Message(content=requirement, cause_by=UserRequirement)
    architect = RequirementBreakdowner(context=ctx)
    while msg:
        architect.put_message(msg)
        msg = await architect.run()


@app.command()
def startup(
    filename: str = typer.Argument(..., help="The filename of original text requirements."),
    namespace: str = typer.Option(default="RFC225", help="Namespace of this project."),
    language: str = typer.Option(
        default="Chinese", help="Which language should be used to write the report. The default language is Chinese."
    ),
    llm_config: str = typer.Option(default="", help="Low-cost LLM config"),
):
    if llm_config and Path(llm_config).exists():
        llm = LLMConfig.load_yaml_file(llm_config)
        config = Config(llm=llm)
    else:
        logger.info("GPT 3.5 turbo is recommended to save money")
        config = Config.default()
    ctx = Context(config=config)
    ctx.kwargs.ns = Namespaces(namespace=namespace)
    ctx.kwargs.language = language
    asyncio.run(breakdown(ctx, filename))


if __name__ == "__main__":
    app()
