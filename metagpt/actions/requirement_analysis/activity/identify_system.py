#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/13
@Author  : mashenquan
@File    : identify_system.py
@Desc    : The implementation of the Chapter 2.2.8 of RFC145.
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
            predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
        )
        actors = [r.subject for r in rows]
        for actor in actors:
            actor_name = remove_affix(split_namespace(actor)[-1])
            await self._identify_one(actor_name)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _identify_one(self, actor_name):
        original_requirement = await self._get_original_requirement()
        prompt = f"## Original Requirement\n{original_requirement}\n---\n\n"
        actor_description = await self._get_actor_detail(actor_name)
        prompt += f"## Actor Detail\n- Name: {actor_name}\n- Description: {actor_description}\n"

        prompt += "\n---\nBased on the above requirement description, "
        prompt += f'does "{actor_name}" refer to the "system" in the Use Case Diagram?'

        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                "You are a tool in the use case diagram for distinguishing between actors and systems.",
                'You need to categorize parts that cannot be developed, such as personnel, organizations, externally manifested systems, etc., into "use case diagram actors"; otherwise, categorize them into "use case diagram systems".',
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
                # system的优先级比actor的高. 如果是actor，那么只能在没有数据的情况下才能insert
                rows = await self.graph_db.select(
                    subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_name)),
                    predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
                )
                if not rows:
                    await self.graph_db.insert(
                        subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_name)),
                        predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
                        object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Actor_),
                    )
                rows = await self.graph_db.select(
                    subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor_name)),
                    predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                )
                if not rows:
                    await self.graph_db.insert(
                        subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor_name)),
                        predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                        object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
                    )
                continue
            # use case
            await self.graph_db.delete(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Actor_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.System_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Not_ + GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Actor_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Has_ + GraphKeyWords.Reason),
                object_=concat_namespace(self.context.kwargs.ns.use_case, add_affix(m.reason)),
            )
            # activity actor
            await self.graph_db.delete(
                subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor_name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_actor, GraphKeyWords.Not_ + GraphKeyWords.Is_
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.System_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor_name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_actor, GraphKeyWords.Has_ + GraphKeyWords.Reason
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(m.reason)),
            )

    async def _get_original_requirement(self) -> str:
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.Is_),
        )
        return remove_affix(split_namespace(rows[0].object_)[-1])

    async def _get_actor_detail(self, name: str) -> str:
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(name)),
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_actor, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        return remove_affix(split_namespace(rows[0].object_)[-1])
