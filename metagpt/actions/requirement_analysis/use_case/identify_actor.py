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


class UseCaseActorDetail(BaseModel):
    actor_name: str
    actor_description: str
    reason: str = ""
    actor_named_reason: str = ""

    def get_markdown(self, indent=0) -> str:
        prefix = "  " * indent
        return prefix + f"- {self.actor_name}: {self.actor_description}\n"


class IdentifyActor(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        self.graph_db = await DiGraphRepository.load_from(self.context.repo.docs.graph_repo.workdir / filename)
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.Is_),
        )
        if not rows:
            rows = await self._insert_requiremnt_to_db()

        rsp = ""
        for r in rows:
            rsp = await self._identify_one(r)
        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content=rsp, cause_by=self)

    async def _insert_requiremnt_to_db(self):
        doc = await self.context.repo.docs.get(filename=REQUIREMENT_FILENAME)
        await self.graph_db.insert(
            subject=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.namespace, add_affix(doc.content)),
        )
        return [
            SPO(
                subject="",
                predicate="",
                object_=concat_namespace(self.context.kwargs.ns.namespace, add_affix(doc.content)),
            )
        ]

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _identify_one(self, spo):
        requirement = remove_affix(split_namespace(spo.object_)[-1])
        rsp = await self.llm.aask(
            requirement,
            system_msgs=[
                "You are a translation tool that converts text into UML 2.0 actors according to the UML 2.0 "
                "standard.",
                "Actor names must be in phrases that clearly describe or represent information related to the original requirements.",
                "Translate each actor's information into a JSON format that includes "
                'a "actor_name" key for the actor\'s name containing the original description phrases referenced '
                "from the original requirements, "
                'an "actor_description" key to describes the actor including the original description phrases or '
                "sentence referenced from the original requirements, "
                'and a "reason" key to explain the basis of the translation, citing specific descriptions from '
                "the original text, "
                'an "actor_named_reason" key explaining the actor name references what modifier from the original requirement and why was it named as such.',
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        for block in json_blocks:
            m = UseCaseActorDetail.model_validate_json(block)
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(m.actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Actor_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(m.actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail),
                object_=concat_namespace(self.context.kwargs.ns.use_case, add_affix(block)),
            )
        return rsp
