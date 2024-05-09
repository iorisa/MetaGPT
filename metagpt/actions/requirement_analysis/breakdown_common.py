#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : breakdown_common.py
@Desc    : Defines common structs that used in breakdown the requirement specifications. The implementation of RFC 225.
"""
from typing import Dict, List, Optional

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
    is_constraint: bool = False
    constraint: Optional[str] = None
    reason: Optional[str] = None


class ReportTableRow(BaseModel):
    name: str
    value: Optional[List[str]] = None
    hint: Optional[List[str]] = None
    issue: Optional[List[str]] = None
    check_list: Optional[List[str]] = None
    risk: Optional[List[str]] = None
    risk_prevention: Optional[List[str]] = None

    def merge(self, r: "ReportTableRow") -> bool:
        if self.name != r.name:
            return False
        for name in self.model_fields.keys():
            if name == "name":
                continue
            v1 = getattr(self, name)
            v2 = getattr(r, name)
            if not v1 and not v2:
                continue
            merged = (v1 or []) + (v2 or [])
            setattr(self, name, merged)

    @property
    def markdown_table_row(self):
        fields = []
        columns = ReportTableRow.model_fields.keys()
        for name in columns:
            v = getattr(self, name)
            if name == "name":
                fields.append(v)
                continue
            if v:
                lines = [f"{i + 1}. " + v.replace("\n", "<br/>").replace("|", "\|") for i, v in enumerate(v)]
                fields.append("<br>".join(lines))
            else:
                fields.append("")
        return "|" + "|".join(fields) + "|"


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

    @property
    def has_issue(self) -> bool:
        return not self.who or not self.when

    @property
    def rows(self) -> List[ReportTableRow]:
        result = []
        who = ReportTableRow(name="who")
        if self.who:
            who.value = [self.who]
        else:
            who.risk = [
                "Stakeholder unknown",
                "Requirements can be misinterpreted",
                "No acceptance criteria",
                "No acceptor",
            ]
            who.risk_prevention = ["Refine the requirements description"]
        result.append(who)
        if self.what:
            result.append(ReportTableRow(name="what", value=[self.what]))
        when = ReportTableRow(name="when")
        if self.when:
            when.value = [self.when]
        else:
            when.risk = [
                "The scene description is vague",
                "The timing of the problem is unclear",
                "The requirement description is incomplete",
            ]
            when.risk_prevention = ["Refine the requirements description"]
        result.append(when)
        if self.why:
            result.append(ReportTableRow(name="why", value=[self.why]))
        if self.how:
            result.append(ReportTableRow(name="how", value=[self.how]))
        return result


class IssueWhatPatch(BaseModel):
    is_clear: bool
    is_actionable: bool
    data_for_checks: List[str]
    measurement_tools_and_methods: List[str]
    indicators: List[str]
    avoiding_subjective_issues: List[str]
    criteria: List[str]
    quality_requirements: List[str]

    @property
    def has_risk(self) -> bool:
        return not self.is_clear or not self.is_actionable

    @property
    def rows(self) -> List[ReportTableRow]:
        result = []
        if not self.is_clear:
            result.append(
                ReportTableRow(
                    name="is_clear",
                    risk=["Objectives and indicators are unclear"],
                    risk_prevention=["Refine the requirements description"],
                )
            )
        if not self.is_actionable:
            result.append(
                ReportTableRow(
                    name="is_actionable",
                    risk=["Not actionable and checkable"],
                    risk_prevention=["Refine the requirements description"],
                )
            )
        result.append(ReportTableRow(name="data_for_checks", hint=self.data_for_checks))
        result.append(ReportTableRow(name="measurement_tools_and_methods", hint=self.measurement_tools_and_methods))
        result.append(ReportTableRow(name="indicators", hint=self.indicators))
        result.append(ReportTableRow(name="avoiding_subjective_issues", hint=self.avoiding_subjective_issues))
        result.append(ReportTableRow(name="criteria", hint=self.criteria))
        result.append(ReportTableRow(name="quality_requirements", hint=self.quality_requirements))

        return result


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

    @property
    def has_risk(self) -> bool:
        return bool(self.potential_risks)

    @property
    def rows(self) -> List[ReportTableRow]:
        result = [
            ReportTableRow(name="objectives", hint=self.objectives),
            ReportTableRow(name="expected_outcomes", check_list=self.expected_outcomes),
            ReportTableRow(name="criteria", hint=self.criteria),
            ReportTableRow(name="quality_requirements", check_list=self.quality_requirements),
            ReportTableRow(name="inputs_needs", check_list=self.inputs_needs),
            ReportTableRow(name="external_environmental_factors", hint=self.external_environmental_factors),
            ReportTableRow(
                name="potential_risks/risk_prevention", risk=self.potential_risks, risk_prevention=self.risk_prevention
            ),
            ReportTableRow(name="expected_outputs", check_list=self.expected_outputs),
        ]
        return result


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

    @property
    def has_risk(self) -> bool:
        return bool(self.potential_risks)

    @property
    def rows(self) -> List[ReportTableRow]:
        result = [
            ReportTableRow(name="objectives", value=self.objectives),
            ReportTableRow(name="expected_outputs", check_list=self.expected_outputs),
            ReportTableRow(name="criteria", hint=self.criteria),
            ReportTableRow(name="quality_requirements", check_list=self.quality_requirements),
            ReportTableRow(name="evaluations", check_list=self.evaluations),
            ReportTableRow(name="inputs_needs", check_list=self.inputs_needs),
            ReportTableRow(name="steps", hint=self.steps),
            ReportTableRow(name="methods", hint=self.methods),
            ReportTableRow(name="technologies", hint=self.technologies),
            ReportTableRow(name="external_environmental_factors", hint=self.external_environmental_factors),
            ReportTableRow(
                name="potential_risks/risk_prevention", risk=self.potential_risks, risk_prevention=self.risk_prevention
            ),
        ]
        return result


class AnalysisReport(BaseModel):
    use_case_detail: BreakdownUseCaseDetail
    reference_type: BreakdownReferenceType
    issue_5w1h: Optional[Issue5W1H] = None
    what: Optional[IssueWhatPatch] = None
    todo: Optional[ToDoPatch] = None
    effect: Optional[EffectPatch] = None

    @property
    def table(self) -> Dict[str, ReportTableRow]:
        rows = []
        if self.issue_5w1h:
            rows.extend(self.issue_5w1h.rows)
        if self.what:
            rows.extend(self.what.rows)
        if self.todo:
            rows.extend(self.todo.rows)
        if self.effect:
            rows.extend(self.effect.rows)
        table = {}
        for i in rows:
            item = table.get(i.name)
            if not item:
                table[i.name] = i
                continue
            item.merge(i)
        return table

    @property
    def markdown_table(self) -> str:
        columns = list(ReportTableRow.model_fields.keys())
        rows = [
            "|" + "|".join(columns) + "|",
            "|:--" * len(columns) + "|",
        ]
        table = self.table
        keys = list(table.keys())
        keys.sort()
        for k in keys:
            i = table[k]
            rows.append(i.markdown_table_row)

        return "\n".join(rows)

    @property
    def has_risk(self) -> bool:
        if self.issue_5w1h and self.issue_5w1h.has_issue:
            return True
        if self.what and self.what.has_risk:
            return True
        if self.todo and self.todo.has_risk:
            return True
        if self.effect and self.effect.has_risk:
            return True
        return False

    @property
    def use_case(self) -> str:
        return self.use_case_detail.use_case

    @property
    def tags(self) -> List[str]:
        tags = sorted(self.use_case_detail.tags, key=lambda x: x.level)
        return [i.tag for i in tags]

    @property
    def reference(self) -> str:
        return self.reference_type.reference

    @property
    def is_constraint(self) -> bool:
        return self.reference_type.is_constraint or len(self.table) == 0
