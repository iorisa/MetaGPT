#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_use_case.py
@Desc    : The implementation of the Chapter 2.2.4 of RFC145.
"""
from pydantic import BaseModel

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.config import CONFIG
from metagpt.const import GRAPH_REPO_FILE_REPO
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


class IdentifyUseCase(Action):
    async def run(self, with_messages: Message, schema: str = CONFIG.prompt_schema):
        graph_repo_pathname = CONFIG.git_repo.workdir / GRAPH_REPO_FILE_REPO / CONFIG.git_repo.workdir.name
        graph_db = await DiGraphRepository.load_from(str(graph_repo_pathname.with_suffix(".json")))

        rows = await graph_db.select(
            subject=concat_namespace(CONFIG.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(CONFIG.namespace, GraphKeyWords.Is),
        )

        for r in rows:
            ns, val = split_namespace(r.object_)
            requirement = remove_affix(val)
            rsp = await self.llm.aask(
                requirement,
                system_msgs=[
                    "You are a translation tool that converts text into UML 2.0 use cases according to the UML 2.0 standard.",
                    'Translate the information of each use case into JSON format. Use a "name" key for the title of the use case starting with a verb, a "description" key for a summary of the use case, a "detail" key to describe the specific operations to be carried out in the use case, a "goal" key to explain the problem the use case aims to solve, and a "reason" key to provide the basis for the translation, citing specific descriptions from the original text.',
                ],
            )
            logger.info(rsp)
            json_blocks = parse_json_code_block(rsp)

            class _JsonCodeBlock(BaseModel):
                name: str
                description: str
                detail: str
                goal: str
                reason: str

            use_case_namespace = concat_namespace(CONFIG.namespace, GraphKeyWords.UseCase, delimiter="_")
            for block in json_blocks:
                m = _JsonCodeBlock.model_validate_json(block)
                await graph_db.insert(
                    subject=concat_namespace(use_case_namespace, add_affix(m.name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                    object_=concat_namespace(use_case_namespace, GraphKeyWords.useCase),
                )
                await graph_db.insert(
                    subject=concat_namespace(use_case_namespace, add_affix(m.name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.hasDetail),
                    object_=concat_namespace(use_case_namespace, add_affix(block)),
                )
        await graph_db.save()
        return Message(content=rsp, cause_by=self)
