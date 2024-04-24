#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : identify_use_case.py
@Desc    : The implementation of the Chapter 2.2.1 of RFC225.
"""
from pathlib import Path
from typing import List, Optional

from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions import Action
from metagpt.actions.requirement_analysis.breakdown_common import (
    BreakdownUseCaseDetail,
    BreakdownUseCaseList,
    Section,
    Sections,
)
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
        self.graph_db = await DiGraphRepository.load_from(self.context.repo.docs.graph_repo.workdir / filename)

        rows = await self.graph_db.select(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown, GraphKeyWords.OriginalRequirement + GraphKeyWords.List
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown, GraphKeyWords.Is_),
        )
        sections = Sections.model_validate_json(remove_affix(split_namespace(rows[0].object_)[-1]))
        use_cases = BreakdownUseCaseList()
        for i in sections.sections:
            use_case_list = await self._extract(i)
            use_cases.use_cases.extend(use_case_list)

        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case, GraphKeyWords.OriginalRequirement + GraphKeyWords.List
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.breakdown_use_case, add_affix(use_cases.model_dump_json())),
        )

        await self.graph_db.save()

        await self.repo.docs.use_case.save(filename="all.json", content=use_cases.model_dump_json())
        await self._save_use_cases_pdf()

        return Message(content="", cause_by=self)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _extract(self, section: Section) -> List[BreakdownUseCaseDetail]:
        rsp = await self.llm.aask(
            section.content,
            system_msgs=[
                "You are a tool capable of converting original text into a list of use cases.",
                'Generate use cases based on the content in "Original Text".',
                "Return a markdown JSON object with:\n"
                'a "use_cases" key containing a list of objects. Each object contains:\n'
                '- a "use_case" key containing the description of the use case;\n'
                '- a "references" key containing a string list of the intact original text sentences related to the use case, as referenced from "Original Text";\n'
                '- a "reason" key explaining why.',
            ],
            stream=True,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        details = BreakdownUseCaseList.model_validate_json(json_blocks[0])
        for i in details.use_cases:
            i.tags = section.tags
        await self.graph_db.insert(
            subject=concat_namespace(self.context.kwargs.ns.breakdown_use_case, add_affix(section.model_dump_json())),
            predicate=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
            object_=concat_namespace(self.context.kwargs.ns.breakdown_use_case, add_affix(details.model_dump_json())),
        )
        return details.use_cases

    async def _save_use_cases_pdf(self):
        rows = await self.graph_db.select(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case, GraphKeyWords.OriginalRequirement + GraphKeyWords.List
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case, GraphKeyWords.Is_),
        )
        use_cases = BreakdownUseCaseList.model_validate_json(remove_affix(split_namespace(rows[0].object_)[-1]))
        md = "|Use Case|References|Reason|Tags|\n|:--|:--|:--|:--|\n"
        for i in use_cases.use_cases:
            fields = [
                i.use_case,
                "<br>".join([v.replace("\n", "<br>").replace("|", "\\|") for v in i.references]),
                i.reason,
                "<br>".join([v.tag for v in i.tags]),
            ]
            row = "|" + "|".join(fields) + "|\n"
            md += row

        await self.context.repo.resources.use_case.save(filename="all.md", content=md)
