#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_actor.py
@Desc    : The implementation of the Chapter 2.2.7 of RFC145.
"""
from pathlib import Path
from typing import List

from pydantic import BaseModel

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    add_affix,
    concat_namespace,
    json_to_markdown_prompt,
    parse_json_code_block,
    remove_affix,
    split_namespace,
)
from metagpt.utils.di_graph_repository import DiGraphRepository


class IdentifyActor(Action):
    async def run(self, with_messages: Message = None):
        filename = Path(self.project_repo.workdir.name).with_suffix(".json")
        doc = await self.project_repo.docs.graph_repo.get(filename)
        graph_db = DiGraphRepository(name=filename).load_json(doc.content)
        activity_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Activity, delimiter="_")
        rows = await graph_db.select(predicate=concat_namespace(activity_namespace, GraphKeyWords.hasDetail))

        class _JsonCodeBlock(BaseModel):
            actors: List[str]
            reason: str

        for r in rows:
            ns, detail = split_namespace(r.object_)
            detail = remove_affix(detail)
            prompt = json_to_markdown_prompt(detail, include={"recipients": [], "performers": []})
            rsp = await self.llm.aask(
                prompt,
                system_msgs=[
                    "You are a UML 2.0 actor detector.",
                    "You need to examine the relationship between performers and recipients with actions, "
                    "identifying hidden actors not explicitly mentioned in the context.",
                    "Actor names must clearly represent information related to the original requirements; "
                    'the use of generic terms like "user", "actor" and "system" is prohibited.',
                    "Return a markdown JSON format includes "
                    'an "actors" key for the list of actors, '
                    'a "reason" key explaining why.',
                ],
            )
            logger.info(rsp)
            json_blocks = parse_json_code_block(rsp)

            activity_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Activity, delimiter="_")
            use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
            for block in json_blocks:
                m = _JsonCodeBlock.model_validate_json(block)
                for actor in m.actors:
                    await graph_db.insert(
                        subject=concat_namespace(activity_namespace, add_affix(actor)),
                        predicate=concat_namespace(activity_namespace, GraphKeyWords.Is),
                        object_=concat_namespace(activity_namespace, GraphKeyWords.actor),
                    )
                    await graph_db.insert(
                        subject=concat_namespace(use_case_namespace, add_affix(actor)),
                        predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                        object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
                    )
                    await graph_db.insert(
                        subject=concat_namespace(use_case_namespace, add_affix(actor)),
                        predicate=concat_namespace(use_case_namespace, GraphKeyWords.associate),
                        object_=r.subject,
                    )
                    await graph_db.insert(
                        subject=r.subject,
                        predicate=concat_namespace(use_case_namespace, GraphKeyWords.associate),
                        object_=concat_namespace(use_case_namespace, add_affix(actor)),
                    )

        await self.project_repo.docs.graph_repo.save(filename=filename, content=graph_db.json())
        return Message(content="", cause_by=self)
