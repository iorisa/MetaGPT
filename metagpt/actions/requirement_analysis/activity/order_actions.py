#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : sort_actions.py
@Desc    : The implementation of the Chapter 2.2.14 of RFC145.
"""
from pathlib import Path
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.activity_common import (
    ActionList,
    ActionOrders,
)
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.use_case_common import UseCaseDetail
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
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import SPO, GraphRepository


class OrderActions(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        self.graph_db = await DiGraphRepository.load_from(self.context.repo.docs.graph_repo.workdir / filename)
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.UseCase_),
        )
        for r in rows:
            await self._order_use_case(r.subject)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    async def _order_use_case(self, ns_use_case_name: str):
        rows = await self.graph_db.select(
            subject=ns_use_case_name,
            predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail),
        )
        use_case_detail_spo = rows[0]
        rows = await self.graph_db.select(
            subject=ns_use_case_name,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_action, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        action_list_detail_spo = rows[0]
        prompt = self._write_prompt(use_case_detail=use_case_detail_spo, action_list_detail=action_list_detail_spo)

        orders = await self._order(prompt)

        await self.graph_db.insert(
            subject=ns_use_case_name,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_control_flow, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
            object_=concat_namespace(self.context.kwargs.ns.activity_control_flow, add_affix(orders.model_dump_json())),
        )
        await self.graph_db.insert(
            subject=concat_namespace(self.context.kwargs.ns.activity_control_flow, add_affix(orders.model_dump_json())),
            predicate=concat_namespace(self.context.kwargs.ns.activity_control_flow, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.activity_control_flow, GraphKeyWords.ControlFlow_),
        )
        for cf in orders.detail:
            await self.graph_db.insert(
                subject=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action, add_affix(cf.action_name)
                ),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action, add_affix(cf.model_dump_json())
                ),
            )
            await self.graph_db.insert(
                subject=concat_namespace(
                    self.context.kwargs.ns.activity_control_flow_action, add_affix(cf.action_name)
                ),
                predicate=concat_namespace(self.context.kwargs.ns.activity_control_flow_action, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_control_flow_action, GraphKeyWords.Action_),
            )

    @staticmethod
    def _write_prompt(use_case_detail: SPO, action_list_detail: SPO) -> str:
        _, v = split_namespace(use_case_detail.object_)
        uc_detail = UseCaseDetail.model_validate_json(remove_affix(v))
        prompt = "## Use Case\n"
        prompt += uc_detail.get_markdown()

        prompt += "\n---\n"
        _, v = split_namespace(action_list_detail.object_)
        al_detail = ActionList.model_validate_json(remove_affix(v))
        prompt += "## Action List\n"
        prompt += al_detail.get_markdown()

        return prompt

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _order(self, prompt: str) -> ActionOrders:
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool to order a shuffled action list of a use case.",
                "Return a markdown JSON object with a `detail` key which lists each action with "
                'a "pre_actions" key for actions this action depends on and should be performed before this action, '
                'an "action_name" key for the name of the action, '
                'a "post_actions" key for actions directly depend on this action be performed, '
                'An "if_conditions" key lists all the condition descriptions based on the values of parameters that need to be satisfied for the execution of the current action if any, '
                'a "reason" key explaining why.',
            ],
            stream=False,
        )

        json_blocks = parse_json_code_block(rsp)
        for block in json_blocks:
            return ActionOrders.model_validate_json(block)
        return ActionOrders()
