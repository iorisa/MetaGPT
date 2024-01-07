#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : enrich_use_case.py
@Desc    : The implementation of the Chapter 2.2.6 of RFC145.
"""
from typing import List

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
from metagpt.utils.graph_repository import GraphRepository


class EnrichUseCase(Action):
    async def run(self, with_messages: Message, schema: str = CONFIG.prompt_schema):
        graph_repo_pathname = CONFIG.git_repo.workdir / GRAPH_REPO_FILE_REPO / CONFIG.git_repo.workdir.name
        graph_db = await DiGraphRepository.load_from(str(graph_repo_pathname.with_suffix(".json")))
        use_case_namespace = concat_namespace(CONFIG.namespace, GraphKeyWords.UseCase, delimiter="_")
        use_case_names = await graph_db.select(
            predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
            object_=concat_namespace(use_case_namespace, GraphKeyWords.useCase),
        )
        for use_case_name in use_case_names:
            rows = await graph_db.select(
                subject=use_case_name.subject, predicate=concat_namespace(use_case_namespace, GraphKeyWords.hasDetail)
            )
            for r in rows:
                ns, val = split_namespace(r.object_)
                detail = remove_affix(val)
                await self._enrich_use_case(graph_db, use_case_name.subject, detail)
        await graph_db.save()
        return Message(content="", cause_by=self)

    async def _enrich_use_case(self, graph_db: GraphRepository, ns_use_case_name: str, use_case_detail: str):
        rsp = await self.llm.aask(
            use_case_detail,
            system_msgs=[
                "You are a tool that translates UML use case text into markdown a JSON format.",
                'Actor names must convey information relevant to the requirements; the use of generic terms like "user", "actor" and "system" is prohibited.',
                'Transform the given use case text into a Markdown JSON object that includes a "actors" key to list relevant actors, an "inputs" key to list relevant use case inputs, an "outputs" key to list relevant use case outputs, an "actions" key to list the consecutive actions that need to be performed, and a "reason" key explaining why.',
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        class _JsonCodeBlock(BaseModel):
            actors: List[str]
            inputs: List[str]
            outputs: List[str]
            actions: List[str]
            reason: str

        activity_namespace = concat_namespace(CONFIG.namespace, GraphKeyWords.Activity, delimiter="_")
        for block in json_blocks:
            m = _JsonCodeBlock.model_validate_json(block)
            await graph_db.insert(
                subject=ns_use_case_name,
                predicate=concat_namespace(activity_namespace, GraphKeyWords.hasDetail),
                object_=concat_namespace(activity_namespace, add_affix(block)),
            )
            for actor in m.actors:
                await graph_db.insert(
                    subject=ns_use_case_name,
                    predicate=concat_namespace(activity_namespace, GraphKeyWords.hasActor),
                    object_=concat_namespace(activity_namespace, add_affix(actor)),
                )
            for input in m.inputs:
                await graph_db.insert(
                    subject=ns_use_case_name,
                    predicate=concat_namespace(activity_namespace, GraphKeyWords.hasInput),
                    object_=concat_namespace(activity_namespace, add_affix(input)),
                )
            for output in m.outputs:
                await graph_db.insert(
                    subject=ns_use_case_name,
                    predicate=concat_namespace(activity_namespace, GraphKeyWords.hasOutput),
                    object_=concat_namespace(activity_namespace, add_affix(output)),
                )
            for action in m.actions:
                await graph_db.insert(
                    subject=ns_use_case_name,
                    predicate=concat_namespace(activity_namespace, GraphKeyWords.hasAction),
                    object_=concat_namespace(activity_namespace, add_affix(action)),
                )
            await graph_db.insert(
                subject=ns_use_case_name,
                predicate=concat_namespace(activity_namespace, GraphKeyWords.hasReason),
                object_=concat_namespace(activity_namespace, add_affix(m.reason)),
            )
        await graph_db.save()
        return Message(content=rsp, cause_by=self)
