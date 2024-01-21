#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/13
@Author  : mashenquan
@File    : identify_actor.py
@Desc    : The implementation of the Chapter 2.2.7 of RFC145.
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
    json_to_markdown_prompt,
    parse_json_code_block,
    remove_affix,
    split_namespace,
)
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphRepository


class ActorAction(BaseModel):
    performing_actor: str
    action_name: str
    recipient_actor: str
    reason: str


class UseCaseActorActionDetail(BaseModel):
    detail: List[ActorAction]
    actors: List[UseCaseActorDetail]


class IdentifyActor(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        self.graph_db = await DiGraphRepository.load_from(self.context.repo.docs.graph_repo.workdir / filename)
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail
            )
        )

        for r in rows:
            await self._identify_one(r)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _identify_one(self, spo):
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.Is_),
        )
        original_requirement = remove_affix(split_namespace(rows[0].object_)[-1])
        prompt = f"## Original Requirements\n{original_requirement}\n"
        prompt += "\n---\n"

        actors = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Actor_),
        )
        prompt += "## Actor List\n"
        for r in actors:
            affixed_actor_name = split_namespace(r.subject)[-1]
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_actor, affixed_actor_name),
                predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
            )
            rows = await self.graph_db.select(
                subject=r.subject,
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail),
            )
            json_data = remove_affix(split_namespace(rows[0].object_)[-1])
            actor = UseCaseActorDetail.model_validate_json(json_data)
            prompt += actor.get_markdown()
        prompt += "\n---\n"

        detail = remove_affix(split_namespace(spo.object_)[-1])
        prompt += json_to_markdown_prompt(detail)
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                "You are a UML 2.0 actor detector tool.",
                "You need to examine the relationship between performers and recipients through actions, matching each action with its possible performer and recipient. "
                'If neither of the actors in the "Actor List" matches the action, you can add a new actor.',
                "Return a markdown JSON object with:\n"
                'an "detail" key list all action objects, each action object contains:\n'
                '  - a "performing_actor" key for the name of performing actor containing the original description phrases referenced from the original requirements, '
                '  - an "action_name" key for the name of the action performed by the performer actor, '
                '  - a "recipient_actor" key for the name of recipient actor containing the original description phrases referenced from the original requirements, '
                '  - a "reason" key explaining why. '
                'an "actors" key list all actor objects, each actor object contains:\n'
                '  - an "actor_name" key for the actor\'s name, '
                '  - an "actor_description" key to describes the actor including the original description phrases or '
                "sentence referenced from the original requirements.",
            ],
            stream=False,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        data = UseCaseActorActionDetail.model_validate_json(json_blocks[0])

        await self.graph_db.insert(
            subject=spo.subject,  # ns_use_case
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_actor_action,
                GraphKeyWords.Has_ + GraphKeyWords.Extend + GraphKeyWords.Detail,
            ),
            object_=concat_namespace(self.context.kwargs.ns.activity_actor_action, add_affix(data.model_dump_json())),
        )
        for actor in data.actors:
            await self.graph_db.insert(
                subject=spo.subject,  # ns_use_case
                predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Associate_),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor.actor_name)),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor.actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor.actor_name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_actor, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor.actor_description)),
            )
            rows = await self.graph_db.select(
                subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor.actor_name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
            )
            if not rows:
                await self.graph_db.insert(
                    subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor.actor_name)),
                    predicate=concat_namespace(
                        self.context.kwargs.ns.activity_actor, GraphKeyWords.Has_ + GraphKeyWords.Detail
                    ),
                    object_=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor.model_dump_json())),
                )
                await self.graph_db.insert(
                    subject=concat_namespace(self.context.kwargs.ns.activity_actor, add_affix(actor.actor_name)),
                    predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                    object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
                )
