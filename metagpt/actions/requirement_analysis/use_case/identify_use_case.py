#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_use_case.py
@Desc    : The implementation of the Chapter 2.2.4 of RFC145.
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


class IdentifyUseCase(Action):
    graph_db: Optional[GraphRepository] = None

    async def run(self, with_messages: Message = None):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        doc = await self.context.repo.docs.graph_repo.get(filename=filename)
        graph_db = DiGraphRepository(name=filename).load_json(doc.content)

        rows = await graph_db.select(
            subject=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Is),
        )
        rsp = ""
        for r in rows:
            rsp = self._identify_one(spo=r)
        await self.project_repo.docs.graph_repo.save(filename=filename, content=graph_db.json())
        return Message(content=rsp, cause_by=self)

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
                "You are a translation tool that converts text into UML 2.0 use cases according to the UML 2.0 "
                "standard.",
                "Translate the information from each use case into a single markdown JSON format. ",
                'Use a "name" key for the title of the use case starting with a verb, '
                'a "description" key for a summary of the use case, '
                'a "detail" key to describe the specific operations to be carried out in the use case, '
                'a "goal" key to explain the problem the use case aims to solve, '
                'a "references" key to list all original description phrases or sentences referred from the '
                "original requirements, "
                'a potentially "performers" key to list all original description phrases that describe entities '
                "performing actions in the use case, "
                'a potentially empty "recipients" key to list all original description phrases describing entities '
                "that are the target of actions in the use case, "
                'and a "reason" key to provide the basis for the translation, citing specific descriptions from '
                "the original text.",
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        class _JsonCodeBlock(BaseModel):
            name: str
            description: str
            detail: str
            goal: str
            references: List[str]
            performers: Optional[List[str]] = None
            recipients: Optional[List[str]] = None
            reason: str

        use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
        for block in json_blocks:
            m = _JsonCodeBlock.model_validate_json(block)
            await self.graph_db.insert(
                subject=concat_namespace(use_case_namespace, add_affix(m.name)),
                predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                object_=concat_namespace(use_case_namespace, GraphKeyWords.useCase),
            )
            await self.graph_db.insert(
                subject=concat_namespace(use_case_namespace, add_affix(m.name)),
                predicate=concat_namespace(use_case_namespace, GraphKeyWords.hasDetail),
                object_=concat_namespace(use_case_namespace, add_affix(block)),
            )
        return rsp
