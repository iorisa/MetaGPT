#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : identify_output.py
@Desc    : The implementation of the Chapter 2.2.11 of RFC145.
"""

from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions.requirement_analysis import GraphDBAction
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
from metagpt.utils.graph_repository import SPO


class IdentifyOutput(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail
            )
        )
        for r in rows:
            ns, _ = split_namespace(r.subject)
            if ns != self.context.kwargs.ns.use_case:
                continue
            await self._parse_output(r)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _parse_output(self, spo: SPO):
        use_case_detail = remove_affix(split_namespace(spo.object_)[-1])
        prompt = json_to_markdown_prompt(use_case_detail)
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool that analyzes use case descriptions and generates a list of all possible outputs produced by the use case.",
                'Return a Markdown JSON object with all possible outputs listed under the "outputs" key, which contains a list of output objects. Each output object has a "name" key containing the title, a "description" key containing the output description, and a "reason" key providing explanations.',
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
                    self.context.kwargs.ns.activity_use_case_output, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_use_case_output, add_affix(m.model_dump_json())
                ),
            )
            for i in m.outputs:
                await self.graph_db.insert(
                    subject=spo.subject,
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_use_case_output, GraphKeyWords.Has_ + GraphKeyWords.Output
                    ),
                    object_=concat_namespace(
                        self.context.kwargs.ns.activity_use_case_output, add_affix(i.model_dump_json())
                    ),
                )
                await self.graph_db.insert(
                    subject=concat_namespace(
                        self.context.kwargs.ns.activity_use_case_output, add_affix(i.model_dump_json())
                    ),
                    predicate=concat_namespace(self.context.kwargs.ns.activity_use_case_output, GraphKeyWords.Is_),
                    object_=concat_namespace(self.context.kwargs.ns.activity_use_case_output, GraphKeyWords.Output_),
                )
