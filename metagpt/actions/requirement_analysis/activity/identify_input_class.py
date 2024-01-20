#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : identify_input_class.py
@Desc    : The implementation of the Chapter 2.2.12 of RFC145.
"""
from pathlib import Path
from typing import Optional

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.text_to_class import text_to_class
from metagpt.schema import Message
from metagpt.utils.common import add_affix, concat_namespace, remove_affix
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import SPO, GraphRepository


class IdentifyInputClass(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        doc = await self.context.repo.docs.graph_repo.get(filename)
        self.graph_db = DiGraphRepository(name=filename).load_json(doc.content)
        activity_namespace = concat_namespace(
            self.context.kwargs.namespace, GraphKeyWords.Activity, GraphKeyWords.Input, delimiter="_"
        )
        rows = await self.graph_db.select(predicate=concat_namespace(activity_namespace, GraphKeyWords.hasDetail))
        for r in rows:
            await self._parse_class(r)
        return Message(content="", cause_by=self)

    async def _parse_class(self, spo: SPO):
        detail = remove_affix(spo.object_)
        classes = await text_to_class(detail=detail, llm=self.context.llm)

        activity_namespace = concat_namespace(
            self.context.kwargs.namespace,
            GraphKeyWords.Activity,
            GraphKeyWords.Input,
            GraphKeyWords.Class,
            delimiter="_",
        )
        for class_ in classes:
            await self.graph_db.insert(
                subject=spo.subject,
                predicate=concat_namespace(activity_namespace, GraphKeyWords.hasClass),
                object_=concat_namespace(activity_namespace, add_affix(class_.name)),
            )
            await self.graph_db.insert(
                subject=concat_namespace(activity_namespace, add_affix(class_.name)),
                predicate=concat_namespace(activity_namespace, GraphKeyWords.Is),
                object_=concat_namespace(activity_namespace, GraphKeyWords.class_),
            )
            for prop in class_.properties:
                await self.graph_db.insert(
                    subject=concat_namespace(activity_namespace, add_affix(class_.name)),
                    predicate=concat_namespace(activity_namespace, GraphKeyWords.hasProperty),
                    object_=concat_namespace(activity_namespace, add_affix(prop)),
                )
        await self.graph_db.save()
