#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : classify_use_case.py
@Desc    : The implementation of the Chapter 2.2.2 of RFC225.
"""

from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.breakdown_common import (
    BreakdownReferenceType,
    BreakdownUseCaseDetail,
    BreakdownUseCaseList,
)
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    add_affix,
    concat_namespace,
    general_after_log,
    parse_json_code_block,
    remove_affix,
    split_namespace,
)


class ClassifyUseCase(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()

        rows = await self.graph_db.select(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case, GraphKeyWords.OriginalRequirement + GraphKeyWords.List
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case, GraphKeyWords.Is_),
        )
        use_cases = BreakdownUseCaseList.model_validate_json(remove_affix(split_namespace(rows[0].object_)[-1]))
        for i in use_cases.use_cases:
            await self._classify(i)

        await self.graph_db.save()

        return Message(content="", cause_by=self)

    async def _classify(self, use_case: BreakdownUseCaseDetail):
        for i in use_case.references:
            await self._classify_reference(i, use_case)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _classify_reference(self, reference: str, use_case: BreakdownUseCaseDetail):
        prompt = "## Use Case\n" + reference
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                'Does the "Use Case" explicitly address the issue of this requirement?',
                'Does the "Use Case" explicitly specify how this requirement should be done?',
                'Does the "Use Case" explicitly state what effect this requirement requires?',
                "Why?",
                "Return a markdown JSON object with:\n"
                '- an "is_issue" key with a boolean value;\n'
                '- an "issue" key containing the original text of "Use Case" related to the issue if "is_issue" is true;\n'
                '- an "is_todo" key with a boolean value;\n'
                '- a "todo" key containing the original text of "Use Case" related to how this requirement should be done if "is_todo" is true;\n'
                '- an "is_effect" key with a boolean value;\n'
                '- an "effect" key containing the original text of "Use Case" related to what effect this requirement requires;\n'
                '- a "reason" key explaining why.\n',
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        type_ = BreakdownReferenceType.model_validate_json(json_blocks[0])
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference, add_affix(use_case.model_dump_json())
            ),
            predicate=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference, GraphKeyWords.Has_ + GraphKeyWords.Reference
            ),
            object_=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference, add_affix(type_.model_dump_json())
            ),
        )
