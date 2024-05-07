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
    reference: Optional[str] = None
    is_issue: bool = False
    issue: Optional[str] = None
    is_todo: bool = False
    todo: Optional[str] = None
    is_effect: bool = False
    effect: Optional[str] = None
    reason: Optional[str] = None


class Issue5W1H(BaseModel):
    who: str
    why_who: str
    what: str
    why_what: str
    when: str
    why_when: str
    why: str
    why_why: str
    how: str
    why_how: str


class IssueWhatPatch(BaseModel):
    is_clear: bool
    is_actionable: bool
    data_for_checks: List[str]
    measurement_tools_and_methods: List[str]
    indicators: List[str]
    avoiding_subjective_issues: List[str]
    criteria: List[str]
    quality_requirements: List[str]


class ToDoPatch(BaseModel):
    objectives: List[str]
    expected_outcomes: List[str]
    criteria: List[str]
    quality_requirements: List[str]
    inputs_needs: List[str]
    external_environmental_factors: List[str]
    potential_risks: List[str]
    risk_prevention: List[str]
    expected_outputs: List[str]


class EffectPatch(BaseModel):
    objectives: List[str]
    expected_outputs: List[str]
    criteria: List[str]
    quality_requirements: List[str]
    is_measurable: bool
    evaluations: List[str]
    inputs_needs: List[str]
    steps: List[str]
    methods: List[str]
    technologies: List[str]
    external_environmental_factors: List[str]
    potential_risks: List[str]
    risk_prevention: List[str]
