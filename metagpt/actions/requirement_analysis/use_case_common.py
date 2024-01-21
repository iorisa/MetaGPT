#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : use_case_common.py
@Desc    : Defines common structs that used in use case views.
"""
from typing import List, Optional

from pydantic import BaseModel


class UseCaseDetail(BaseModel):
    name: str
    description: str
    actions: str
    goal: str
    references: List[str]
    performers: Optional[List[str]] = None
    recipients: Optional[List[str]] = None
    reason: str

    def get_markdown(self, heading: int = 2) -> str:
        prefix = "#" * heading
        md = f"{prefix}# {self.name}\n"
        md += f"{prefix}## Description\n{self.description}\n"
        md += f"{prefix}## Actions\n{self.actions}\n"
        md += f"{prefix}## Goal\n{self.goal}\n"
        if self.performers:
            md += f"{prefix}## Performers\n" + "".join([f"- {i}\n" for i in self.performers])
        if self.recipients:
            md += f"{prefix}## Recipients\n" + "".join([f"- {i}\n" for i in self.recipients])
        return md
