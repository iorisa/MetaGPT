#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : patch_use_case.py
@Desc    : The implementation of the Chapter 2.2.3 of RFC225.
"""

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.breakdown_common import (
    BreakdownReferenceType,
    BreakdownUseCaseDetail,
    Issue5W1H,
    IssueWhatPatch,
    Section,
    Sections,
)
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
        if type_.is_todo:
            await self._patch_todo(use_case_detail, type_, section)
        if type_.is_effect:
            await self._patch_effect(use_case_detail, type_, section)

    async def _patch_issue(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        original_text = section.content
        issue = type_.reference
        prompt = f"## Original Text\n{original_text}\n## Use Case\n{use_case_detail.use_case}\n## Issue\n{issue}\n"
        language = self.context.kwargs.language or "Chinese"
        rsp = await self.llm.aask(
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
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        what = Issue5W1H.model_validate_json(json_blocks[0])
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case_reference_what, GraphKeyWords.Is_),
            object_=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(what.model_dump_json())
            ),
        )

        await self._patch_issue_what(
            original_text=original_text, use_case_detail=use_case_detail, issue=issue, what=what
        )
        pass

    async def _patch_issue_what(
        self, original_text: str, use_case_detail: BreakdownUseCaseDetail, issue: str, what: Issue5W1H
    ):
        prompt = (
            f"## Original Text\n{original_text}\n"
            f"## Use Case\n{use_case_detail.use_case}\n"
            f"## Issue\n{issue}\n"
            f"### What\n{what.what}\n"
            f"### Why\n{what.why}\n"
        )
        language = self.context.kwargs.language or "Chinese"
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                '"Use Case" is meant to address the problems raised in the "Issue";',
                '"Original Text" provides the complete context information;',
                '"Issue" has been broken down with "5W1H" method.',
                'Is the description in "What" able to establish clear objectives and indicators?',
                'Is the description in "What" actionable and checkable? If so:\n'
                "- How can the data for checks be obtained? Provide sufficiently specific guidance.\n"
                "- Which measurement tools and methods should be used? Provide sufficiently specific guidance.\n"
                "- Which indicators should be selected? Provide sufficiently specific guidance.\n"
                "- How to avoid subjective issues in measurement results? Provide sufficiently specific guidance.\n"
                "- What are the criteria for solving the issue? What are the quality requirements when solving the issue? Provide sufficiently specific guidance.",
                "Return a markdown JSON object with:\n"
                '- a "is_clear" key containing a boolean key about whether the description in "What" able to establish clear objectives and indicators;\n'
                '- a "is_actionable" key containing a boolean key about whether the description in "What" actionable and checkable;\n'
                '- a "data_for_checks" key containing a string list type of object about how the data for checks can be obtained with sufficiently specific guidance if "is_actionable" is filled with true;\n'
                '- a "measurement_tools_and_methods" key containing a string  list type object about which measurement tools and methods are used with sufficiently specific guidance if "is_actionable" is filled with true;\n'
                '- a "indicators" key containing a string list type object about which indicators are selected with sufficiently specific guidance   if "is_actionable" is filled with true;\n'
                '- a "avoiding_subjective_issues" key containing a string list type object about how to avoid subjective issues in measurement results  with sufficiently specific guidance   if "is_actionable" is filled with true;\n',
                '- a "criteria" key containing a string list type object about what the criteria are for solving the issue;\n'
                '- a "quality_requirements" key containing a string list type object about what the quality requirements are when solving the issue;\n'
                f"- Answer in {language} language.",
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        patch = IssueWhatPatch.model_validate_json(json_blocks[0])
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
            object_=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(patch.model_dump_json())
            ),
        )

    async def _patch_todo(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        pass

    async def _patch_effect(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        pass
