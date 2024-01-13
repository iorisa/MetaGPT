#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/13
@Author  : mashenquan
@File    : identify_system.py
@Desc    : The implementation of the Chapter 2.2.8 of RFC145.
"""
from pathlib import Path

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


class IdentifySystem(Action):
    async def run(self, with_messages: Message = None):
        filename = Path(self.project_repo.workdir.name).with_suffix(".json")
        doc = await self.project_repo.docs.graph_repo.get(filename)
        graph_db = DiGraphRepository(name=filename).load_json(doc.content)
        activity_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Activity, delimiter="_")
        use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
        rows = await graph_db.select(
            predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
            object_=concat_namespace(use_case_namespace, GraphKeyWords.useCase),
        )
        use_case_names = [r.subject for r in rows]
        use_case_details = set()
        for use_case_name in use_case_names:
            rows = await graph_db.select(
                subject=use_case_name, predicate=concat_namespace(activity_namespace, GraphKeyWords.hasDetail)
            )
            for r in rows:
                ns, detail = split_namespace(r.object_)
                use_case_details.add(remove_affix(detail))

        rows = await graph_db.select(
            predicate=concat_namespace(activity_namespace, GraphKeyWords.Is),
            object_=concat_namespace(activity_namespace, GraphKeyWords.actor),
        )
        actors = [r.subject for r in rows]

        for use_case_detail in use_case_details:
            for actor in actors:
                prompt = "## Use Case\n"
                prompt += json_to_markdown_prompt(use_case_detail, depth=3)
                ns, actor_name = split_namespace(actor)
                prompt += f"## Actor Name\n{remove_affix(actor_name)}\n\n---\n"

                prompt += "## Actor Description\n"
                rows = await graph_db.select(
                    subject=actor, predicate=concat_namespace(activity_namespace, GraphKeyWords.hasDetail)
                )
                descriptions = []
                for r in rows:
                    ns, actor_description = split_namespace(r.object_)
                    descriptions.append(remove_affix(actor_description))
                prompt += "\n".join(descriptions)
                prompt += "\n---\n"

                rsp = await self.llm.aask(
                    prompt,
                    system_msgs=[
                        "You are a UML 2.0 system checker tool.",
                        'Based on the content of "Actor Description" and "Use Case", determine whether the current actor is the system in UML 2.0 use case.',
                        'Return a JSON format in Markdown including an "is_system" key with boolean value, a "reason" key explaining why.',
                    ],
                )
                logger.info(rsp)
                json_blocks = parse_json_code_block(rsp)

                class _JsonCodeBlock(BaseModel):
                    is_system: bool
                    reason: str

                for block in json_blocks:
                    m = _JsonCodeBlock.model_validate_json(block)
                    if not m.is_system:
                        continue

                    await graph_db.insert(
                        subject=actor,
                        predicate=concat_namespace(activity_namespace, GraphKeyWords.Is),
                        object_=concat_namespace(activity_namespace, GraphKeyWords.system_),
                    )
                    await graph_db.delete(
                        subject=actor,
                        predicate=concat_namespace(activity_namespace, GraphKeyWords.Is),
                        object_=concat_namespace(activity_namespace, GraphKeyWords.actor),
                    )
                    await graph_db.insert(
                        subject=actor,
                        predicate=concat_namespace(activity_namespace, GraphKeyWords.notIs),
                        object_=concat_namespace(activity_namespace, GraphKeyWords.actor),
                    )
                    await graph_db.insert(
                        subject=actor,
                        predicate=concat_namespace(activity_namespace, GraphKeyWords.hasReason),
                        object_=concat_namespace(activity_namespace, add_affix(m.reason)),
                    )

                    await graph_db.insert(
                        subject=concat_namespace(use_case_namespace, actor_name),
                        predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                        object_=concat_namespace(use_case_namespace, GraphKeyWords.system_),
                    )
                    await graph_db.delete(
                        subject=concat_namespace(use_case_namespace, actor_name),
                        predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                        object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
                    )
                    await graph_db.insert(
                        subject=concat_namespace(use_case_namespace, actor_name),
                        predicate=concat_namespace(use_case_namespace, GraphKeyWords.notIs),
                        object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
                    )
                    await graph_db.insert(
                        subject=concat_namespace(use_case_namespace, actor_name),
                        predicate=concat_namespace(use_case_namespace, GraphKeyWords.hasReason),
                        object_=concat_namespace(use_case_namespace, add_affix(m.reason)),
                    )

        return Message(content="", cause_by=self)
