#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : requirement_analyze.py
@Desc    : The implementation of RFC145. https://deepwisdom.feishu.cn/docx/VhRCdcfQQoIlaJxWvyLcMDP9nbg
"""
import asyncio

import typer

from metagpt.actions import UserRequirement
from metagpt.actions.prepare_documents import PrepareDocuments
from metagpt.actions.requirement_analysis import activity, use_case
from metagpt.config import CONFIG
from metagpt.roles import Role
from metagpt.schema import Message
from metagpt.utils.common import any_to_str, aread

app = typer.Typer(add_completion=False)


class RequirementAnalyzer(Role):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Set events or actions the Architect should watch or be aware of
        self._watch(
            {
                UserRequirement,
                PrepareDocuments,
                use_case.IdentifyActor,
                use_case.IdentifyUseCase,
                use_case.IdentifySystem,
                activity.EnrichUseCase,
            }
        )

    async def _observe(self, ignore_memory=False) -> int:
        return await super()._observe(ignore_memory=True)

    async def _think(self) -> bool:
        handlers = {
            any_to_str(UserRequirement): PrepareDocuments(),
            any_to_str(PrepareDocuments): use_case.IdentifyActor(),
            any_to_str(use_case.IdentifyActor): use_case.IdentifyUseCase(),
            any_to_str(use_case.IdentifyUseCase): use_case.IdentifySystem(),
            any_to_str(use_case.IdentifySystem): activity.EnrichUseCase(),
        }
        self.rc.todo = handlers.get(self.rc.news[0].cause_by, None)
        return bool(self.rc.todo is not None)


async def analyze(requirement_filename: str):
    requirement = await aread(filename=requirement_filename, encoding="utf-8")
    msg = Message(content=requirement, cause_by=UserRequirement)
    architect = RequirementAnalyzer()
    while msg:
        architect.put_message(msg)
        msg = await architect.run()


@app.command()
def startup(
    filename: str = typer.Argument(..., help="The filename of original text requirements."),
    namespace: str = typer.Argument("RFC145", help="Namespace of this project."),
):
    CONFIG.namespace = namespace
    asyncio.run(analyze(filename))


if __name__ == "__main__":
    app()
