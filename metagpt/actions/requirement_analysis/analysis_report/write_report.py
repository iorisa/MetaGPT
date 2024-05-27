#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/5/7
@Author  : mashenquan
@File    : patch_use_case.py
@Desc    : The implementation of the Chapter 2.2.4 of RFC225.
"""
from typing import List, Optional

from pydantic import Field
from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.breakdown_common import (
    AnalysisReport,
    BreakdownReferenceType,
    BreakdownUseCaseDetail,
    EffectPatch,
    Issue5W1H,
    IssueWhatPatch,
    ToDoPatch,
)
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    add_affix,
    concat_namespace,
    general_after_log,
    remove_affix,
    split_namespace,
)


class WriteReport(GraphDBAction):
    unready: List[str] = Field(default_factory=list)
    raw_unready: List[str] = Field(default_factory=list)
    ready: List[str] = Field(default_factory=list)
    raw_ready: List[str] = Field(default_factory=list)
    constraint: List[str] = Field(default_factory=list)
    raw_constraint: List[str] = Field(default_factory=list)

    async def run(self, with_messages: Message = None):
        await self.load_graph_db()
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference, GraphKeyWords.Has_ + GraphKeyWords.Reference
            )
        )
        for i in rows:
            use_case_detail = BreakdownUseCaseDetail.model_validate_json(remove_affix(split_namespace(i.subject)[-1]))
            type_ = BreakdownReferenceType.model_validate_json(remove_affix(split_namespace(i.object_)[-1]))
            report = await self._report(use_case_detail=use_case_detail, type_=type_)

            if report.has_risk:
                no = len(self.unready) + 1
            elif report.is_constraint:
                no = len(self.constraint) + 1
            else:
                no = len(self.ready) + 1
            content = f"## {no}. {report.use_case}\n"
            content += f"### {no}.1. Paragraph\n" + "\n".join([f"- {i}" for i in report.tags]) + "\n"
            content += f"### {no}.2. Reference\n{report.reference}\n"
            if not report.is_constraint:
                content += f"### {no}.3. Summary\n{report.markdown_table}\n"

            rsp = await self._translate(content)
            if report.has_risk:
                self.unready.append(rsp)
                self.raw_unready.append(content)
                continue
            if report.is_constraint:
                self.constraint.append(rsp)
                self.raw_constraint.append(content)
                continue
            self.ready.append(rsp)
            self.raw_ready.append(content)

        await self.context.repo.resources.requirement_analysis.save(
            filename="unready.md", content="\n\n---\n\n".join(self.unready)
        )
        await self.context.repo.resources.requirement_analysis.save(
            filename="ready.md", content="\n\n---\n\n".join(self.ready)
        )
        await self.context.repo.resources.requirement_analysis.save(
            filename="constraint.md", content="\n\n---\n\n".join(self.constraint)
        )

        await self.context.repo.resources.requirement_analysis.save(
            filename="raw-unready.md", content="\n\n---\n\n".join(self.raw_unready)
        )
        await self.context.repo.resources.requirement_analysis.save(
            filename="raw-ready.md", content="\n\n---\n\n".join(self.raw_ready)
        )
        await self.context.repo.resources.requirement_analysis.save(
            filename="raw-constraint.md", content="\n\n---\n\n".join(self.raw_constraint)
        )

        await self.graph_db.save()
        return Message(content="", cause_by=self)

    async def _report(self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType) -> AnalysisReport:
        issue, patch_what = await self._get_issue(use_case_detail)
        patch_todo = await self._get_todo(use_case_detail)
        patch_effect = await self._get_effect(use_case_detail)
        report = AnalysisReport(
            use_case_detail=use_case_detail,
            reference_type=type_,
            issue_5w1h=issue,
            what=patch_what,
            todo=patch_todo,
            effect=patch_effect,
        )
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_report, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case_reference_report, GraphKeyWords.Is_),
            object_=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_report, add_affix(report.model_dump_json())
            ),
        )
        return report

    async def _get_issue(
        self, use_case_detail: BreakdownUseCaseDetail
    ) -> (Optional[Issue5W1H], Optional[IssueWhatPatch]):
        what_rows = await self.graph_db.select(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(use_case_detail.model_dump_json())
            )
        )
        issue: Issue5W1H = None
        patch_what: IssueWhatPatch = None
        for r in what_rows:
            if r.predicate == concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, GraphKeyWords.Is_
            ):
                issue = Issue5W1H.model_validate_json(remove_affix(split_namespace(r.object_)[-1]))
            elif r.predicate == concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ):
                patch_what = IssueWhatPatch.model_validate_json(remove_affix(split_namespace(r.object_)[-1]))
        return issue, patch_what

    async def _get_todo(self, use_case_detail: BreakdownUseCaseDetail) -> Optional[ToDoPatch]:
        todo_rows = await self.graph_db.select(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_todo, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case_reference_todo, GraphKeyWords.Is_),
        )
        if not todo_rows:
            return None
        todo = ToDoPatch.model_validate_json(remove_affix(split_namespace(todo_rows[0].object_)[-1]))
        return todo

    async def _get_effect(self, use_case_detail: BreakdownUseCaseDetail) -> EffectPatch:
        effect_rows = await self.graph_db.select(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_effect, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case_reference_effect, GraphKeyWords.Is_),
        )
        if not effect_rows:
            return None
        effect = EffectPatch.model_validate_json(remove_affix(split_namespace(effect_rows[0].object_)[-1]))
        return effect

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _translate(self, content) -> str:
        language = self.context.kwargs.language or "Chinese"
        rsp = await self.llm.aask(
            content,
            system_msgs=[
                f"You are a tool for translating other languages into {language}",
                "Translation cannot change the original markdown document format",
            ],
        )
        return rsp
