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
from metagpt.actions.requirement_analysis import (
    activity,
    merge_swimlane,
    summarize,
    use_case,
)
from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.context import Context
from metagpt.logs import logger
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
                activity.IdentifyActor,
                activity.IdentifySystem,
                activity.IdentifyInput,
                activity.IdentifyAction,
                activity.IdentifyOutput,
                activity.IdentifyInputClass,
                activity.IdentifyOutputClass,
                activity.OrderActions,
                merge_swimlane.ActionMergeSwimlane,
                merge_swimlane.MergeActionDAG,
                merge_swimlane.MergeDataFlow,
                summarize.Summarize,
            }
        )

    async def _observe(self, ignore_memory=False) -> int:
        return await super()._observe(ignore_memory=True)

    async def _think(self) -> bool:
        handlers = {
            any_to_str(UserRequirement): PrepareDocuments(context=self.context),
            any_to_str(PrepareDocuments): use_case.IdentifyActor(context=self.context),
            any_to_str(use_case.IdentifyActor): use_case.IdentifyUseCase(context=self.context),
            any_to_str(use_case.IdentifyUseCase): use_case.IdentifySystem(context=self.context),
            any_to_str(use_case.IdentifySystem): activity.EnrichUseCase(context=self.context),
            any_to_str(activity.EnrichUseCase): activity.IdentifyActor(context=self.context),
            any_to_str(activity.IdentifyActor): activity.IdentifySystem(context=self.context),
            any_to_str(activity.IdentifySystem): activity.IdentifyInput(context=self.context),
            any_to_str(activity.IdentifyInput): activity.IdentifyAction(context=self.context),
            any_to_str(activity.IdentifyAction): activity.IdentifyOutput(context=self.context),
            any_to_str(activity.IdentifyOutput): activity.IdentifyInputClass(context=self.context),
            any_to_str(activity.IdentifyInputClass): activity.IdentifyOutputClass(context=self.context),
            any_to_str(activity.IdentifyOutputClass): activity.OrderActions(context=self.context),
            any_to_str(activity.OrderActions): merge_swimlane.ActionMergeSwimlane(context=self.context),
            any_to_str(merge_swimlane.ActionMergeSwimlane): merge_swimlane.MergeActionDAG(context=self.context),
            any_to_str(merge_swimlane.MergeActionDAG): merge_swimlane.MergeDataFlow(context=self.context),
            any_to_str(merge_swimlane.MergeDataFlow): summarize.Summarize(context=self.context),
        }
        self.rc.todo = handlers.get(self.rc.news[0].cause_by, None)
        return bool(self.rc.todo is not None)


async def analyze(ctx: Context, requirement_filename: str):
    requirement = await aread(filename=requirement_filename, encoding="utf-8")
    msg = Message(content=requirement, cause_by=UserRequirement)
    architect = RequirementAnalyzer(context=ctx)
    while msg:
        architect.put_message(msg)
        msg = await architect.run()


@app.command()
def startup(
    filename: str = typer.Argument(..., help="The filename of original text requirements."),
    namespace: str = typer.Argument("RFC145", help="Namespace of this project."),
):
    logger.info("GPT 3.5 turbo is recommended to save money")
    ctx = Context()
    ctx.kwargs.ns = Namespaces(namespace=namespace)
    asyncio.run(analyze(ctx, filename))


if __name__ == "__main__":
    app()
