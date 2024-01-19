#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_actor.py
@Desc    : The implementation of the Chapter 2.2.3 of RFC145.
"""
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.const import REQUIREMENT_FILENAME
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


class IdentifyActor(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        self.graph_db = DiGraphRepository(name=filename)
        doc = await self.project_repo.docs.graph_repo.get(filename)
        if doc:
            self.graph_db.load_json(doc.content)
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Is),
        )
        if not rows:
            rows = await self._insert_requiremnt_to_db()

        rsp = ""
        for r in rows:
            rsp = await self._identify_one(r)
        await self.context.repo.docs.graph_repo.save(filename=filename, content=self.graph_db.json())
        return Message(content=rsp, cause_by=self)

    async def _insert_requiremnt_to_db(self):
        doc = await self.context.repo.docs.get(filename=REQUIREMENT_FILENAME)
        await self.graph_db.insert(
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

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _identify_one(self, spo):
        ns, val = split_namespace(spo.object_)
        requirement = remove_affix(val)
        rsp = await self.llm.aask(
            requirement,
            system_msgs=[
                "You are a translation tool that converts text into UML 2.0 actors according to the UML 2.0 "
                "standard.",
                "Actor names must clearly represent information related to the original requirements; "
                'the use of generic terms like "user", "actor" and "system" is prohibited.',
                "Translate each actor's information into a JSON format that includes "
                'a "actor_name" key for the actor\'s name containing the original description phrases referenced '
                "from the original requirements, "
                'an "actor_description" key to describes the actor including the original description phrases or '
                "sentence referenced from the original requirements, "
                'and a "reason" key to explain the basis of the translation, citing specific descriptions from '
                "the original text.",
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
            await self.graph_db.insert(
                subject=concat_namespace(use_case_namespace, add_affix(m.actor_name)),
                predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
            )
            await self.graph_db.insert(
                subject=concat_namespace(use_case_namespace, add_affix(m.actor_name)),
                predicate=concat_namespace(use_case_namespace, GraphKeyWords.hasDetail),
                object_=concat_namespace(use_case_namespace, add_affix(block)),
            )
        return rsp
