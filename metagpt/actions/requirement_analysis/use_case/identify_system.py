#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_system.py
@Desc    : The implementation of the Chapter 2.2.5 of RFC145.
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
    parse_json_code_block,
    remove_affix,
    split_namespace,
)
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphRepository


class IdentifySystem(Action):
    async def run(self, with_messages: Message = None):
        filename = Path(self.project_repo.workdir.name).with_suffix(".json")
        doc = await self.project_repo.docs.graph_repo.get(filename=filename)
        graph_db = DiGraphRepository(name=filename).load_json(doc.content)

        rows = await graph_db.select(
            subject=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Is),
        )

        for r in rows:
            ns, val = split_namespace(r.object_)
            requirement = remove_affix(val)
            await self._identify_system(graph_db, requirement)
        await self.project_repo.docs.graph_repo.save(filename=filename, content=graph_db.json())
        return Message(content="", cause_by=self)

    async def _identify_system(self, graph_db: GraphRepository, requirement: str):
        use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
        rows = await graph_db.select(
            predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
            object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
        )
        for r in rows:
            ns, val = split_namespace(r.subject)
            actor_name = remove_affix(val)
            prompt = f'{requirement}\nn\n---\nBased on the above requirement description, does "{actor_name}" refer to the "system" in the Use Case Diagram?'
            rsp = await self.llm.aask(
                prompt,
                system_msgs=[
                    'You are an actor classification tool based on the UML 2.0 standard. Your responsibility is to distinguish whether a specified actor represents the "system" in the Use Case Diagram.',
                    'Return a JSON object in Markdown format with an "is_system" key containing a boolean value, and a "reason" key explaining why.',
                ],
            )
            logger.info(rsp)
            json_blocks = parse_json_code_block(rsp)

            class _JsonCodeBlock(BaseModel):
                is_system: bool
                reason: str

            use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase)
            for block in json_blocks:
                m = _JsonCodeBlock.model_validate_json(block)
                if not m.is_system:
                    continue
                await graph_db.insert(
                    subject=concat_namespace(use_case_namespace, add_affix(actor_name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                    object_=concat_namespace(use_case_namespace, GraphKeyWords.system_),
                )
                await graph_db.delete(
                    subject=concat_namespace(use_case_namespace, add_affix(actor_name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                    object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
                )
                await graph_db.insert(
                    subject=concat_namespace(use_case_namespace, add_affix(actor_name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.notIs),
                    object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
                )
