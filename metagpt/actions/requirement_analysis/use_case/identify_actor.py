#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : identify_actor.py
@Desc    : The implementation of the Chapter 2.2.3 of RFC145.
"""

from pydantic import BaseModel

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.config import CONFIG
from metagpt.const import DOCS_FILE_REPO, GRAPH_REPO_FILE_REPO, REQUIREMENT_FILENAME
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
from metagpt.utils.file_repository import FileRepository
from metagpt.utils.graph_repository import SPO


class IdentifyActor(Action):
    async def run(self, with_messages: Message, schema: str = CONFIG.prompt_schema):
        graph_repo_pathname = CONFIG.git_repo.workdir / GRAPH_REPO_FILE_REPO / CONFIG.git_repo.workdir.name
        graph_db = await DiGraphRepository.load_from(str(graph_repo_pathname.with_suffix(".json")))
        rows = await graph_db.select(
            subject=concat_namespace(CONFIG.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(CONFIG.namespace, GraphKeyWords.Is),
        )
        if not rows:
            rows = await IdentifyActor._insert_requiremnt_to_db(graph_db=graph_db)

        for r in rows:
            ns, val = split_namespace(r.object_)
            requirement = remove_affix(val)
            rsp = await self.llm.aask(
                requirement,
                system_msgs=[
                    "You are a translation tool that converts text into UML 2.0 actors according to the UML 2.0 standard.",
                    'Actor names must convey information relevant to the requirements; the use of generic terms like "user", "actor" and "system" is prohibited.',
                    'Translate each actor\'s information into a JSON format with keys "actor_name", "actor_description", and a "reason" key to explain the basis of the translation, citing specific descriptions from the original text.',
                ],
            )
            logger.info(rsp)
            json_blocks = parse_json_code_block(rsp)

            class _JsonCodeBlock(BaseModel):
                actor_name: str
                actor_description: str
                reason: str

            use_case_namespace = concat_namespace(CONFIG.namespace, GraphKeyWords.UseCase, delimiter="_")
            for block in json_blocks:
                m = _JsonCodeBlock.model_validate_json(block)
                await graph_db.insert(
                    subject=concat_namespace(use_case_namespace, add_affix(m.actor_name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.Is),
                    object_=concat_namespace(use_case_namespace, GraphKeyWords.actor),
                )
                await graph_db.insert(
                    subject=concat_namespace(use_case_namespace, add_affix(m.actor_name)),
                    predicate=concat_namespace(use_case_namespace, GraphKeyWords.hasDetail),
                    object_=concat_namespace(use_case_namespace, add_affix(block)),
                )
        await graph_db.save()
        return Message(content=rsp, cause_by=self)

    @staticmethod
    async def _insert_requiremnt_to_db(graph_db):
        doc = await FileRepository.get_file(filename=REQUIREMENT_FILENAME, relative_path=DOCS_FILE_REPO)
        await graph_db.insert(
            subject=concat_namespace(CONFIG.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(CONFIG.namespace, GraphKeyWords.Is),
            object_=concat_namespace(CONFIG.namespace, add_affix(doc.content)),
        )
        return [SPO(subject="", predicate="", object_=concat_namespace(CONFIG.namespace, add_affix(doc.content)))]
