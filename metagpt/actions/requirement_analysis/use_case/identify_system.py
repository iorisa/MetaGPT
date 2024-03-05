#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_system.py
@Desc    : The implementation of the Chapter 2.2.5 of RFC145.
"""
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.use_case.identify_actor import (
    UseCaseActorDetail,
)
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
from metagpt.utils.graph_repository import GraphRepository


class IdentifySystem(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        self.graph_db = await DiGraphRepository.load_from(self.context.repo.docs.graph_repo.workdir / filename)

        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.Is_),
        )
        original_requirement = remove_affix(split_namespace(rows[0].object_)[-1])
        await self._identify_system(original_requirement)
        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    async def _identify_system(self, requirement: str):
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Actor_),
        )
        for r in rows:
            await self._identify_one(spo=r, requirement=requirement)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _identify_one(self, spo, requirement):
        actor_detail = await self._get_detail(spo.subject)
        prompt = (
            f"## Original Requirement\n{requirement}\n\n---\n"
            f"## Actor Detail\n- Name: {actor_detail.actor_name}\n- Description: {actor_detail.actor_description}\n"
            f"\n---\nBased on the above requirement description, "
            f'does "{actor_detail.actor_name}" refer to the "system" in the Use Case Diagram?'
        )
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                "You are a tool in the use case diagram for distinguishing between actors and systems.",
                'You need to categorize parts that cannot be developed, such as personnel, organizations, externally manifested systems, into "use case diagram actors"; otherwise, categorize them into "use case diagram systems".',
                "Return a markdown JSON object with "
                'an "is_system" key with a true value if the actoris not personnel, organization, or an externally manifested system, '
                'a "references" key listing all evidence strings about your judgment basis from the "Original Requirement", ',
                'a "reason" key explaining why.',
            ],
            stream=False,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        class _JsonCodeBlock(BaseModel):
            is_system: bool
            references: List[str]
            reason: str

        for block in json_blocks:
            m = _JsonCodeBlock.model_validate_json(block)
            if not m.is_system:
                continue
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_detail.actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.System_),
            )
            await self.graph_db.delete(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_detail.actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Actor_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_detail.actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Not_ + GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Actor_),
            )

    async def _get_detail(self, ns_actor_name: str) -> UseCaseActorDetail:
        rows = await self.graph_db.select(
            subject=ns_actor_name,
            predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail),
        )
        json_data = remove_affix(split_namespace(rows[0].object_)[-1])
        return UseCaseActorDetail.model_validate_json(json_data)
