#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : breakdown_common.py
@Desc    : Defines common structs that used in breakdown the requirement specifications. The implementation of RFC 225.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class SectionTag(BaseModel):
    level: int
    tag: str = ""

    def __hash__(self):
        return hash((self.level, self.tag))

    def __eq__(self, other):
        if not isinstance(other, SectionTag):
            return False
        return self.level == other.level and self.tag == other.tag


class Section(BaseModel):
    content: str
    tags: List[SectionTag] = Field(default_factory=list)


class Sections(BaseModel):
    sections: List[Section]


class BreakdownUseCaseDetail(BaseModel):
    use_case: str
    references: List[str] = Field(default_factory=list)
    reason: str
    tags: List[SectionTag] = Field(default_factory=list)


class BreakdownUseCaseList(BaseModel):
    use_cases: List[BreakdownUseCaseDetail] = Field(default_factory=list)


class BreakdownReferenceType(BaseModel):
    is_issue: bool = False
    issue: Optional[str] = None
    is_todo: bool = False
    todo: Optional[str] = None
    is_effect: bool = False
    effect: Optional[str] = None
    reason: Optional[str] = None
