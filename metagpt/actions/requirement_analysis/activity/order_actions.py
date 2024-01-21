#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : sort_actions.py
@Desc    : The implementation of the Chapter 2.2.14 of RFC145.
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
    concat_namespace,
    general_after_log,
    parse_json_code_block,
    remove_affix,
    split_namespace,
)
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphRepository
from metagpt.utils.json_to_markdown import json_to_markdown


class ActionChainNode(BaseModel):
    pre_actions: Optional[List[str]]
    action_name: str
    post_actions: Optional[List[str]]


class OrderActions(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        doc = await self.context.repo.docs.graph_repo.get(filename)
        self.graph_db = DiGraphRepository(name=filename).load_json(doc.content)
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Is),
            object_=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.useCase),
        )
        for r in rows:
            await self._order_use_case(r.subject)

    async def _order_use_case(self, ns_use_case_name: str):
        use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
        await self.graph_db.select(
            subject=ns_use_case_name, predicate=concat_namespace(use_case_namespace, GraphKeyWords.hasDetail)
        )
        activity_action_namespace = concat_namespace(
            self.context.kwargs.namespace, GraphKeyWords.Activity, GraphKeyWords.Action, delimiter="_"
        )
        rows = await self.graph_db.select(
            subject=ns_use_case_name, predicate=concat_namespace(activity_action_namespace, GraphKeyWords.hasAction)
        )
        ns_action_mappings = {}
        action_type = concat_namespace(activity_action_namespace, GraphKeyWords.action)
        for r in rows:
            infos = await self.graph_db.select(subject=r.subject)
            ns_action_mappings[r.subject] = [r for r in infos if r.object_ != action_type]

        prompt = self._write_prompt(
            ns_use_case_name,
        )

        await self._order(prompt)

        return Message(content="", cause_by=self)

    def _write_prompt(self, use_detail, ns_action_mappings) -> str:
        use_case_detail = json_to_markdown(use_detail, exclude=["reason"])

        actions = []
        for ns_action_name, rows in ns_action_mappings.items():
            _, action_name = split_namespace(ns_action_name)
            inputs = []
            outputs = []
            for r in rows:
                _, predicate_type = split_namespace(r.predicate)
                _, affix_name = split_namespace(r.object_)
                name = remove_affix(affix_name)
                if predicate_type == GraphKeyWords.hasInput:
                    inputs.append(name)
                    continue
                elif predicate_type == GraphKeyWords.hasOutput:
                    outputs.append(name)
                    continue
            obj = {"Action Name": action_name, "Inputs": inputs, "Outputs": outputs}
            block = json_to_markdown(obj, depth=3)
            actions.append(block)

        result = f"## Use Case Detail\n{use_case_detail}\n\n---\n"
        result += "## Action List\n"
        result += "\n\n".join(actions)
        return result

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _order(self, prompt: str) -> List[ActionChainNode]:
        rsp = self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool to order a shuffled action list of a use case.",
                'Return each action in JSON objects list of markdown format with a "pre_actions" key for actions this action depends on and should be performed before this action, an "action_name" key for the name of the action, a "post_actions" key for actions directly depend on this action be performed.',
            ],
        )

        json_blocks = parse_json_code_block(rsp)
        return [ActionChainNode.model_validate_json(block) for block in json_blocks]
