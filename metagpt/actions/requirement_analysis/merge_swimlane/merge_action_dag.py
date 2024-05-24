#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/29
@Author  : mashenquan
@File    : merge_action_dag.py
@Desc    : The implementation of the Chapter 2.2.16 of RFC145.
"""
import json
from typing import Optional

from pydantic import BaseModel

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.activity_common import ActionOrders
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    CodeParser,
    add_affix,
    concat_namespace,
    remove_affix,
    split_namespace,
)


class IfStatementArgument(BaseModel):
    name: str
    description: str
    context: Optional[str] = None
    reason: str


class MergeActionDAG(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_control_flow, GraphKeyWords.Has_ + GraphKeyWords.Detail
            )
        )
        for i in rows:
            ns_use_case = i.subject
            json_data = remove_affix(split_namespace(i.object_)[-1])
            actions = ActionOrders.model_validate_json(json_data)
            await self._merge_use_case(ns_use_case=ns_use_case, actions=actions)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    async def _merge_use_case(self, ns_use_case: str, actions: ActionOrders):
        for i in actions.detail:
            pre_actions = i.pre_actions or []
            for j in pre_actions:
                await self.graph_db.insert(
                    subject=concat_namespace(
                        self.context.kwargs.ns.activity_control_flow_action, add_affix(i.action_name)
                    ),
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_control_flow_action, GraphKeyWords.Has_ + GraphKeyWords.PreOp
                    ),
                    object_=concat_namespace(self.context.kwargs.ns.activity_control_flow_action, add_affix(j)),
                )
            if_conditions = i.if_conditions or []
            for j in if_conditions:
                await self.graph_db.insert(
                    subject=concat_namespace(
                        self.context.kwargs.ns.activity_control_flow_action, add_affix(i.action_name)
                    ),
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_control_flow_action_if,
                        GraphKeyWords.Has_ + GraphKeyWords.IfCondition,
                    ),
                    object_=concat_namespace(self.context.kwargs.ns.activity_control_flow_action_if, add_affix(j)),
                )
                await self.graph_db.insert(
                    subject=concat_namespace(self.context.kwargs.ns.activity_control_flow_action_if, add_affix(j)),
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_control_flow_action_if, GraphKeyWords.Is_
                    ),
                    object_=concat_namespace(
                        self.context.kwargs.ns.activity_control_flow_action_if, GraphKeyWords.IfCondition_
                    ),
                )
                await self._split_action_if_condition(action_name=i.action_name, if_condition=j)

    async def _split_action_if_condition(self, action_name: str, if_condition: str):
        prompt = (
            f"{if_condition} is the condition of the 'if' statement. What objects does it use for boolean judgment?"
        )
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are an if statement splitting tool, and you need to ensure that the parts combined after splitting can express the original semantics.",
                "Return a markdown JSON object of a list. Each object in this list should have "
                'a "name" key for the name of object name, '
                'a "description" key for the description of the object, '
                'a "reason" explaining why.',
            ],
            stream=False,
        )
        json_block = CodeParser.parse_code(text=rsp, lang="json", block="")
        if json_block == rsp:
            logger.warning(f"if condition `{if_condition}`: {rsp}")
            return
        vv = [IfStatementArgument.model_validate(i) for i in json.loads(json_block)]
        for i in vv:
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_control_flow_action, add_affix(action_name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action_if_argument,
                    GraphKeyWords.Has_ + GraphKeyWords.IfCondition + GraphKeyWords.Argument,
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action_if_argument, add_affix(i.name)
                ),
            )
            await self.graph_db.insert(
                subject=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action_if_argument, add_affix(i.name)
                ),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action_if_argument, GraphKeyWords.Is_
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action_if_argument,
                    GraphKeyWords.IfCondition_ + GraphKeyWords.Argument,
                ),
            )
            i.context = if_condition
            await self.graph_db.insert(
                subject=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action_if_argument, add_affix(i.name)
                ),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action_if_argument,
                    GraphKeyWords.Has_ + GraphKeyWords.Detail,
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action_if_argument, add_affix(i.model_dump_json())
                ),
            )
