#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : identify_input_class.py
@Desc    : The implementation of the Chapter 2.2.12 of RFC145.
"""

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.text_to_class import text_to_class
from metagpt.schema import Message
from metagpt.utils.common import (
    add_affix,
    concat_namespace,
    remove_affix,
    split_namespace,
)
from metagpt.utils.graph_repository import SPO


class IdentifyInputClass(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_use_case_input, GraphKeyWords.Has_ + GraphKeyWords.Detail
            )
        )
        for r in rows:
            await self._parse_class(r)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    async def _parse_class(self, spo: SPO):
        parameter_list_json_data = remove_affix(split_namespace(spo.object_)[-1])
        classes = await text_to_class(parameter_list_json=parameter_list_json_data, llm=self.llm)
        for class_ in classes:
            await self.graph_db.insert(
                subject=spo.subject,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_input_class, GraphKeyWords.Has_ + GraphKeyWords.Class
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_input_class, add_affix(class_.name)),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_input_class, add_affix(class_.name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_input_class, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_input_class, GraphKeyWords.Class_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_input_class, add_affix(class_.name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_input_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_input_class, add_affix(class_.model_dump_json())
                ),
            )
