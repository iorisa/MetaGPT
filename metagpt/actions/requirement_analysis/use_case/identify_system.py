#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_system.py
@Desc    : The implementation of the Chapter 2.2.5 of RFC145.
"""
from pathlib import Path
from typing import Optional

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
        doc = await self.context.repo.docs.graph_repo.get(filename=filename)
        self.graph_db = DiGraphRepository(name=filename).load_json(doc.content)

        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Is),
        )

        for r in rows:
            ns, val = split_namespace(r.object_)
            requirement = remove_affix(val)
            await self._identify_system(requirement)
        await self.project_repo.docs.graph_repo.save(filename=filename, content=self.graph_db.json())
        return Message(content="", cause_by=self)

    async def _identify_system(self, requirement: str):
        use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
        rows = await self.graph_db.select(
            predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
            object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
        )
        for r in rows:
            await self._identify_one(spo=r, requirement=requirement)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _identify_one(self, spo, requirement):
        ns, val = split_namespace(spo.subject)
        actor_name = remove_affix(val)
        prompt = (
            f"{requirement}\nn\n---\nBased on the above requirement description, "
            f'does "{actor_name}" refer to the "system" in the Use Case Diagram?'
        )
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                "You are an actor classification tool based on the UML 2.0 standard.",
                'Your responsibility is to distinguish whether a specified actor represents the "system" in '
                "the Use Case Diagram.",
                "Return a JSON object in Markdown format with "
                'an "is_system" key containing a boolean value, '
                'and a "reason" key explaining why.',
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
            await self.graph_db.insert(
                subject=concat_namespace(use_case_namespace, add_affix(actor_name)),
                predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                object_=concat_namespace(use_case_namespace, GraphKeyWords.system_),
            )
            await self.graph_db.delete(
                subject=concat_namespace(use_case_namespace, add_affix(actor_name)),
                predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
            )
            await self.graph_db.insert(
                subject=concat_namespace(use_case_namespace, add_affix(actor_name)),
                predicate=concat_namespace(use_case_namespace, GraphKeyWords.notIs),
                object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
            )
