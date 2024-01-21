#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : identify_input.py
@Desc    : The implementation of the Chapter 2.2.9 of RFC145.
"""
from pathlib import Path
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.text_to_class import ParameterList
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
from metagpt.utils.graph_repository import SPO, GraphRepository


class IdentifyInput(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        self.graph_db = await DiGraphRepository.load_from(self.context.repo.docs.graph_repo.workdir / filename)
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail
            )
        )
        for r in rows:
            ns, _ = split_namespace(r.subject)
            if ns != self.context.kwargs.ns.use_case:
                continue
            await self._parse_input(r)
        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _parse_input(self, spo: SPO):
        use_case_detail = remove_affix(split_namespace(spo.object_)[-1])
        prompt = json_to_markdown_prompt(use_case_detail, exclude=["reason"])
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool that analyzes use case descriptions and lists all possible inputs used in a use case.",
                'Return a Markdown JSON object with all possible inputs listed under the "inputs" key, which contains a list of input objects. Each input object has a "name" key containing the title, a "description" key containing the input description, and a "reason" key providing explanations.',
            ],
            stream=False,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        for block in json_blocks:
            m = ParameterList.model_validate_json(block)
            await self.graph_db.insert(
                subject=spo.subject,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_use_case_input, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_use_case_input, add_affix(m.model_dump_json())
                ),
            )
            for i in m.inputs:
                await self.graph_db.insert(
                    subject=spo.subject,
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_use_case_input, GraphKeyWords.Has_ + GraphKeyWords.Input
                    ),
                    object_=concat_namespace(
                        self.context.kwargs.ns.activity_use_case_input, add_affix(i.model_dump_json())
                    ),
                )
                await self.graph_db.insert(
                    subject=concat_namespace(
                        self.context.kwargs.ns.activity_use_case_input, add_affix(i.model_dump_json())
                    ),
                    predicate=concat_namespace(self.context.kwargs.ns.activity_use_case_input, GraphKeyWords.Is_),
                    object_=concat_namespace(self.context.kwargs.ns.activity_use_case_input, GraphKeyWords.Input_),
                )
