#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_actor.py
@Desc    : The implementation of the Chapter 2.2.7 of RFC145.
"""
from pathlib import Path

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.schema import Message
from metagpt.utils.common import concat_namespace
from metagpt.utils.di_graph_repository import DiGraphRepository


class IdentifyActor(Action):
    async def run(self, with_messages: Message = None):
        filename = Path(self.project_repo.workdir.name).with_suffix(".json")
        doc = await self.project_repo.docs.graph_repo.get(filename)
        graph_db = DiGraphRepository(name=filename).load_json(doc.content)
        rows = await graph_db.select(
            predicate=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Activity, GraphKeyWords.hasDetail)
        )
        for r in rows:
            print(r)

        await self.project_repo.docs.graph_repo.save(filename=filename, content=graph_db.json())
