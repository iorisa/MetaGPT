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

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.schema import Message
from metagpt.utils.common import concat_namespace
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphRepository


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

        await self._identify_action_properties(
            ns_use_case_name,
        )

    async def _identify_action_properties(self, ns_action_name, use_detail, ns_action_mappings):
        pass
