#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_actor.py
@Desc    : The implementation of the Chapter 2.2.3 of RFC145.
"""
from pathlib import Path

from pydantic import BaseModel

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.const import REQUIREMENT_FILENAME
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    add_affix,
    concat_namespace,
    parse_json_code_block,
    remove_affix,
    split_namespace,
)
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import SPO


class IdentifyActor(Action):
    async def run(self, with_messages: Message = None):
        filename = Path(self.project_repo.workdir.name).with_suffix(".json")
        graph_db = DiGraphRepository(name=filename)
        doc = await self.project_repo.docs.graph_repo.get(filename)
        if doc:
            graph_db.load_json(doc.content)
        rows = await graph_db.select(
            subject=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Is),
        )
        if not rows:
            rows = await self._insert_requiremnt_to_db(graph_db=graph_db)

        for r in rows:
            ns, val = split_namespace(r.object_)
            requirement = remove_affix(val)
            rsp = await self.llm.aask(
                requirement,
                system_msgs=[
                    "You are a translation tool that converts text into UML 2.0 actors according to the UML 2.0 standard.",
                    'Actor names must convey information relevant to the requirements; the use of generic terms like "user", "actor" and "system" is prohibited.',
                    'Translate each actor\'s information into a JSON format with keys "actor_name", "actor_description", and a "reason" key to explain the basis of the translation, citing specific descriptions from the original text.',
                ],
            )
            logger.info(rsp)
            json_blocks = parse_json_code_block(rsp)

            class _JsonCodeBlock(BaseModel):
                actor_name: str
                actor_description: str
                reason: str

            use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
            for block in json_blocks:
                m = _JsonCodeBlock.model_validate_json(block)
                await graph_db.insert(
                    subject=concat_namespace(use_case_namespace, add_affix(m.actor_name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                    object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
                )
                await graph_db.insert(
                    subject=concat_namespace(use_case_namespace, add_affix(m.actor_name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.hasDetail),
                    object_=concat_namespace(use_case_namespace, add_affix(block)),
                )
        await self.project_repo.docs.graph_repo.save(filename=filename, content=graph_db.json())
        return Message(content=rsp, cause_by=self)

    async def _insert_requiremnt_to_db(self, graph_db):
        doc = await self.project_repo.docs.get(filename=REQUIREMENT_FILENAME)
        await graph_db.insert(
            subject=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Is),
            object_=concat_namespace(self.context.kwargs.namespace, add_affix(doc.content)),
        )
        return [
            SPO(
                subject="",
                predicate="",
                object_=concat_namespace(self.context.kwargs.namespace, add_affix(doc.content)),
            )
        ]
