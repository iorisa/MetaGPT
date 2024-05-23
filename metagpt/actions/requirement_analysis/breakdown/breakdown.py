#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : breakdown.py
@Desc    : The implementation of the Chapter 2.2.1 of RFC225.
"""
import re
from typing import List

import html2text as html2text
import markdown

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.breakdown_common import (
    Section,
    Sections,
    SectionTag,
)
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.const import REQUIREMENT_FILENAME
from metagpt.schema import Message
from metagpt.utils.common import add_affix, concat_namespace


class BreakdownRequirementSpecifications(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()

        await self._split_doc()

        await self.graph_db.save()

        return Message(content="", cause_by=self)

    async def _split_doc(self):
        doc = await self.context.repo.docs.get(filename=REQUIREMENT_FILENAME)
        await self.graph_db.insert(
            subject=concat_namespace(self.context.kwargs.ns.breakdown, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.breakdown, add_affix(doc.content)),
        )

        parts = []
        lvl2_parts = self._split_section(level=2, md=doc.content)
        for i in lvl2_parts:
            lvl3_parts = self._split_section(level=3, md=i.content)
            for j in lvl3_parts:
                j.tags.extend(i.tags)
            parts.extend(lvl3_parts)
        parts = self._soap(parts)
        parts = self._merge_shorts(parts)
        sections = Sections(sections=parts)
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown, GraphKeyWords.OriginalRequirement + GraphKeyWords.List
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.breakdown, add_affix(sections.model_dump_json())),
        )

    @staticmethod
    def _split_section(level: int, md: str) -> List[Section]:
        if not md:
            return []
        left = "\n" + md if md[0] != "\n" else md
        tag = "\n" + "#" * level + " "
        parts = []
        while True:
            ix = left.find(tag, len(tag))
            if ix < 0:
                section = Section(content=left)
                parts.append(section)
                break
            section = Section(content=left[0:ix])
            parts.append(section)
            left = left[ix:]

        pattern = "^" + "#" * level + r"\s+(.*?)$"
        for i in parts:
            lines = i.content.splitlines()
            for line in lines:
                if not line:
                    continue
                matches = re.findall(pattern, line)
                if not matches:
                    continue
                i.tags.append(SectionTag(level=level, tag=matches[0].strip()))
                break
        return parts

    @staticmethod
    def _merge_shorts(parts: List[Section], min_length: int = 50) -> List[Section]:
        result = []
        merged = Section(content="")
        for i in parts:
            merged.content += i.content
            merged.tags = list(set(merged.tags + i.tags))
            if len(merged.content) < min_length:
                continue
            result.append(merged)
            merged = Section(content="")
        if not merged.content:
            return result
        if not result:
            result.append(merged)
        else:
            result[-1].content += merged.content
            result[-1].tags.extend(merged.tags)
        return result

    @staticmethod
    def _soap(parts):
        text_maker = html2text.HTML2Text()
        text_maker.ignore_links = True
        text_maker.ignore_images = True
        text_maker.ignore_emphasis = True

        for i in parts:
            for t in i.tags:
                html = markdown.markdown(t.tag)
                text = text_maker.handle(html)
                t.tag = text.strip()
            html = markdown.markdown(i.content)
            text = text_maker.handle(html)
            i.content = text.strip()
        return parts
