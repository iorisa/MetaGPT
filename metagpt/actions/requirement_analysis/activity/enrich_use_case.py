#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : enrich_use_case.py
@Desc    : The implementation of the Chapter 2.2.6 of RFC145.
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
from metagpt.utils.graph_repository import GraphRepository


class EnrichUseCase(Action):
    async def run(self, with_messages: Message = None):
        filename = Path(self.project_repo.workdir.name).with_suffix(".json")
        doc = await self.project_repo.docs.graph_repo.get(filename=filename)
        graph_db = DiGraphRepository(name=filename).load_json(doc.content)
        use_case_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
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
        await self.project_repo.docs.graph_repo.save(filename=filename, content=graph_db.json())
        return Message(content="", cause_by=self)

    async def _enrich_use_case(self, graph_db: GraphRepository, ns_use_case_name: str, use_case_detail: str):
        prompt = json_to_markdown_prompt(use_case_detail)
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                # "You are a tool that translates UML use case text into markdown a JSON format.",
                # "Use case descriptions should strive to retain the original information as much as possible.",
                # "In cases of missing information, it is permissible to reasonably expand on the original information.",
                # "The names of the performer and recipient must clearly represent information related to the "
                # 'original requirements; the use of generic terms such as "the user"", "the actor", and "the system" '
                # "is prohibited.",
                "You are a tool to enrich use case detail.",
                "You return a Markdown JSON object including "
                'a "references" key to list all original description phrases referred from the original requirements, '
                'an "inputs" key to list relevant use case inputs, an "outputs" key to list relevant use case outputs, '
                'an "actions" key to list the consecutive actions that need to be performed, '
                'and a "reason" key explaining why.',
                'You enrich the "actions" contents by reasonably expanding on the original information. '
                "The content must not contradict the original information.",
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)

        class _JsonCodeBlock(BaseModel):
            references: List[str]
            inputs: List[str]
            outputs: List[str]
            actions: List[str]
            reason: str

        activity_namespace = concat_namespace(self.context.kwargs.namespace, GraphKeyWords.Activity, delimiter="_")
        for block in json_blocks:
            m = _JsonCodeBlock.model_validate_json(block)
            await graph_db.insert(
                subject=ns_use_case_name,
                predicate=concat_namespace(activity_namespace, GraphKeyWords.hasDetail),
                object_=concat_namespace(activity_namespace, add_affix(block)),
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

        await graph_db.save(path=self.project_repo.docs.graph_repo.workdir)
        return Message(content=rsp, cause_by=self)
