#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : patch_use_case.py
@Desc    : The implementation of the Chapter 2.2.3 of RFC225.
"""
import os

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.breakdown_common import (
    BreakdownReferenceType,
    BreakdownUseCaseDetail,
    Section,
    Sections,
)
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.schema import Message
from metagpt.utils.common import concat_namespace, remove_affix, split_namespace


class PatchUseCase(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()
        rows = await self.graph_db.select(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown, GraphKeyWords.OriginalRequirement + GraphKeyWords.List
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown, GraphKeyWords.Is_),
        )
        sections = Sections.model_validate_json(remove_affix(split_namespace(rows[0].object_)[-1]))
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference, GraphKeyWords.Has_ + GraphKeyWords.Reference
            )
        )
        for i in rows:
            use_case_detail = BreakdownUseCaseDetail.model_validate_json(remove_affix(split_namespace(i.subject)[-1]))
            type_ = BreakdownReferenceType.model_validate_json(remove_affix(split_namespace(i.object_)[-1]))
            await self._patch(use_case_detail, type_, sections)

        await self.graph_db.save()

    async def _patch(self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, sections: Sections):
        section = None
        for i in sections.sections:
            if set(i.tags) == set(use_case_detail.tags):
                section = i
                break
        if type_.is_issue:
            await self._patch_issue(use_case_detail, type_, section)
        elif type_.is_todo:
            await self._patch_todo(use_case_detail, type_, section)
        elif type_.is_effect:
            await self._patch_effect(use_case_detail, type_, section)

    async def _patch_issue(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        original_text = section.content
        issue = type_.reference
        prompt = f"## Original Text\n{original_text}\n## Use Case\n{issue}\n## Issue\n{issue}\n"
        language = os.environ.get("LANGUAGE", "Chinese")
        await self.llm.aask(
            prompt,
            system_msgs=[
                '- "Use Case" is meant to address the problems raised in the "Issue";',
                '- "Original Text" provides the complete context information;',
                '- According to the "5W1H" method, Breaking down the "Issue" by quoting the original text from "Original Text". ',
                "Return a markdown JSON object with:\n"
                '- a "who" key containing the use case actors. Leave it blank if it\'s not mentioned.\n'
                '- a "why_who" key explaining why "who" is filled like this.\n'
                '- a "what" key containing what the issue is in detail. Leave it blank if it\'s not mentioned.\n'
                '- a "why_what" key explaining why "what" is filled like this.\n'
                '- a "when" key containing when the scenario of the issue occurs. Leave it blank if it\'s not mentioned.\n'
                '- a "why_when" key explaining why "when" is filled like this.\n'
                '- a "why" key explaining why these scenario is considered as an issue. Leave it blank if it\'s not mentioned.\n'
                '- a "why_why" key explaining why "why" is filled like this.\n'
                '- a "how" key containing who to do. Leave it blank if it\'s not mentioned.\n'
                '- a "why_how" key explaining why "how" is filled like this.\n'
                f"- Answer in {language} language.",
            ],
        )
        pass

    async def _patch_todo(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        pass

    async def _patch_effect(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        pass
