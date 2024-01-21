#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : identify_action.py
@Desc    : The implementation of the Chapter 2.2.10 of RFC145.
"""
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    add_affix,
    concat_namespace,
    general_after_log,
    json_to_markdown_prompt,
    parse_json_code_block,
    remove_affix,
)
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import SPO, GraphRepository


class IdentifyAction(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        doc = await self.context.repo.docs.graph_repo.get(filename)
        self.graph_db = DiGraphRepository(name=filename).load_json(doc.content)
        activity_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Activity, delimiter="_")
        rows = await self.graph_db.select(predicate=concat_namespace(activity_namespace, GraphKeyWords.hasDetail))
        for r in rows:
            await self._parse_action(r)
        return Message(content="", cause_by=self)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _parse_action(self, spo: SPO):
        use_case_detail = remove_affix(spo.object_)
        prompt = json_to_markdown_prompt(use_case_detail)
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool that analyzes use case descriptions and lists all actions used to complete the use case.",
                'Return a JSON object in Markdown format for each possible action, including a "name" key for the title of the action, an "inputs" key to list all inputs of the action, an "outputs" key to list all outputs of the action, and a "reason" key to provide explanations.',
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        class _JsonCodeBlock(BaseModel):
            name: str
            inputs: List[str]
            outputs: List[str]
            reason: str

        for block in json_blocks:
            m = _JsonCodeBlock.model_validate_json(block)
            activity_namespace = concat_namespace(
                self.context.kwargs.namespace, GraphKeyWords.Activity, GraphKeyWords.Action, delimiter="_"
            )

            await self.graph_db.insert(
                subject=spo.subject,
                predicate=concat_namespace(activity_namespace, GraphKeyWords.hasDetail),
                object_=concat_namespace(activity_namespace, add_affix(block)),
            )
            await self.graph_db.insert(
                subject=spo.subject,
                predicate=concat_namespace(activity_namespace, GraphKeyWords.hasAction),
                object_=concat_namespace(activity_namespace, add_affix(m.name)),
            )
            await self.graph_db.insert(
                subject=concat_namespace(activity_namespace, add_affix(m.name)),
                predicate=concat_namespace(activity_namespace, GraphKeyWords.Is),
                object_=concat_namespace(activity_namespace, GraphKeyWords.action),
            )
            for i in m.inputs:
                await self.graph_db.insert(
                    subject=concat_namespace(activity_namespace, add_affix(m.name)),
                    predicate=concat_namespace(activity_namespace, GraphKeyWords.hasInput),
                    object_=concat_namespace(activity_namespace, add_affix(i)),
                )
            for o in m.outputs:
                await self.graph_db.insert(
                    subject=concat_namespace(activity_namespace, add_affix(m.name)),
                    predicate=concat_namespace(activity_namespace, GraphKeyWords.hasOutput),
                    object_=concat_namespace(activity_namespace, add_affix(o)),
                )

        await self.graph_db.save()
