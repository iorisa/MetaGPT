#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : enrich_use_case.py
@Desc    : The implementation of the Chapter 2.2.6 of RFC145.
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
    split_namespace,
)
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphRepository


class ActivityEnrichUseCase(BaseModel):
    references: List[str]
    inputs: List[str]
    outputs: List[str]
    actions: List[str]
    reason: str


class EnrichUseCase(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        self.graph_db = await DiGraphRepository.load_from(self.context.repo.docs.graph_repo.workdir / filename)
        use_case_names = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.UseCase_),
        )
        for use_case_name in use_case_names:
            rows = await self.graph_db.select(
                subject=use_case_name.subject,
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail),
            )
            for r in rows:
                detail = remove_affix(split_namespace(r.object_)[-1])
                await self._enrich_use_case(use_case_name.subject, detail)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _enrich_use_case(self, ns_use_case_name: str, use_case_detail: str):
        prompt = json_to_markdown_prompt(use_case_detail)
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                "You are a tool to enrich use case detail.",
                "You return a Markdown JSON object including "
                'a "references" key to list all original description phrases referred from the original requirements, '
                'an "inputs" key to list relevant use case inputs, an "outputs" key to list relevant use case outputs, '
                'an "actions" key to list the consecutive actions that need to be performed, '
                'and a "reason" key explaining why.',
                'You enrich the "actions" contents by reasonably expanding on the original information. '
                "The content must not contradict the original information.",
            ],
            stream=False,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        for block in json_blocks:
            m = ActivityEnrichUseCase.model_validate_json(block)
            await self.graph_db.insert(
                subject=ns_use_case_name,
                predicate=concat_namespace(self.context.kwargs.ns.activity_use_case, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_use_case, GraphKeyWords.UseCase_),
            )
            await self.graph_db.insert(
                subject=ns_use_case_name,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_use_case, add_affix(m.model_dump_json())),
            )
            await self.graph_db.insert(
                subject=ns_use_case_name,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_use_case, GraphKeyWords.Has_ + GraphKeyWords.Reason
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_use_case, add_affix(m.reason)),
            )
            for input in m.inputs:
                await self.graph_db.insert(
                    subject=ns_use_case_name,
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_input, GraphKeyWords.Has_ + GraphKeyWords.Input
                    ),
                    object_=concat_namespace(self.context.kwargs.ns.activity_input, add_affix(input)),
                )
                await self.graph_db.insert(
                    subject=concat_namespace(self.context.kwargs.ns.activity_input, add_affix(input)),
                    predicate=concat_namespace(self.context.kwargs.ns.activity_input, GraphKeyWords.Is_),
                    object_=concat_namespace(self.context.kwargs.ns.activity_input, GraphKeyWords.Input_),
                )
            for output in m.outputs:
                await self.graph_db.insert(
                    subject=ns_use_case_name,
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_output, GraphKeyWords.Has_ + GraphKeyWords.Output
                    ),
                    object_=concat_namespace(self.context.kwargs.ns.activity_output, add_affix(output)),
                )
                await self.graph_db.insert(
                    subject=concat_namespace(self.context.kwargs.ns.activity_output, add_affix(output)),
                    predicate=concat_namespace(self.context.kwargs.ns.activity_output, GraphKeyWords.Is_),
                    object_=concat_namespace(self.context.kwargs.ns.activity_output, GraphKeyWords.Output_),
                )
            for action in m.actions:
                await self.graph_db.insert(
                    subject=ns_use_case_name,
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_action, GraphKeyWords.Has_ + GraphKeyWords.Action
                    ),
                    object_=concat_namespace(self.context.kwargs.ns.activity_action, add_affix(action)),
                )
                await self.graph_db.insert(
                    subject=concat_namespace(self.context.kwargs.ns.activity_action, add_affix(action)),
                    predicate=concat_namespace(self.context.kwargs.ns.activity_action, GraphKeyWords.Is_),
                    object_=concat_namespace(self.context.kwargs.ns.activity_action, GraphKeyWords.Action_),
                )
