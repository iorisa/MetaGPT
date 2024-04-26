#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : identify_action.py
@Desc    : The implementation of the Chapter 2.2.10 of RFC145.
"""

from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.activity_common import ActionList
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
from metagpt.utils.graph_repository import SPO


class IdentifyAction(GraphDBAction):
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
            await self._parse_action(r)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _parse_action(self, spo: SPO):
        use_case_detail = remove_affix(split_namespace(spo.object_)[-1])
        prompt = json_to_markdown_prompt(use_case_detail, exclude=["reason"])
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool that analyzes use case descriptions and lists all actions used to complete the use case.",
                'Return a Markdown JSON object with all possible actions listed under the "actions" key, which contains a list of action objects. '
                'Each action object has a "name" key containing the title of the action, '
                'a "inputs" key of a string list to list the descriptions of all inputs used by the action, '
                'a "outputs" key of a string list to list the descriptions of all outputs produced by the action, '
                'a "if_condition" key of a string value containing the description of the prerequisites that need to be met for executing the action, '
                'and a "reason" key of a string value providing explanations.',
            ],
            stream=False,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        for block in json_blocks:
            m = ActionList.model_validate_json(block)
            await self.graph_db.insert(
                subject=spo.subject,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_action, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_action, add_affix(m.model_dump_json())),
            )
            for a in m.actions:
                await self.graph_db.insert(
                    subject=spo.subject,
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_action, GraphKeyWords.Has_ + GraphKeyWords.Action
                    ),
                    object_=concat_namespace(self.context.kwargs.ns.activity_action, add_affix(a.name)),
                )
                await self.graph_db.insert(
                    subject=concat_namespace(self.context.kwargs.ns.activity_action, add_affix(a.name)),
                    predicate=concat_namespace(self.context.kwargs.ns.activity_action, GraphKeyWords.Is_),
                    object_=concat_namespace(self.context.kwargs.ns.activity_action, GraphKeyWords.Action_),
                )
                for i in a.inputs:
                    await self.graph_db.insert(
                        subject=concat_namespace(self.context.kwargs.ns.activity_action, add_affix(a.name)),
                        predicate=concat_namespace(
                            self.context.kwargs.ns.activity_action_input, GraphKeyWords.Has_ + GraphKeyWords.Input
                        ),
                        object_=concat_namespace(self.context.kwargs.ns.activity_action_input, add_affix(i)),
                    )
                    await self.graph_db.insert(
                        subject=concat_namespace(self.context.kwargs.ns.activity_action_input, add_affix(i)),
                        predicate=concat_namespace(self.context.kwargs.ns.activity_action_input, GraphKeyWords.Is_),
                        object_=concat_namespace(self.context.kwargs.ns.activity_action_input, GraphKeyWords.Input_),
                    )
                for o in a.outputs:
                    await self.graph_db.insert(
                        subject=concat_namespace(self.context.kwargs.ns.activity_action, add_affix(a.name)),
                        predicate=concat_namespace(
                            self.context.kwargs.ns.activity_action_output, GraphKeyWords.Has_ + GraphKeyWords.Output
                        ),
                        object_=concat_namespace(self.context.kwargs.ns.activity_action_output, add_affix(o)),
                    )
                    await self.graph_db.insert(
                        subject=concat_namespace(self.context.kwargs.ns.activity_action_output, add_affix(o)),
                        predicate=concat_namespace(self.context.kwargs.ns.activity_action_output, GraphKeyWords.Is_),
                        object_=concat_namespace(self.context.kwargs.ns.activity_action_output, GraphKeyWords.Output_),
                    )
