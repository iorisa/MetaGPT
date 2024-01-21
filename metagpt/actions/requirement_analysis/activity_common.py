#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : activity_common.py
@Desc    : Defines common structs that used in activity views.
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from metagpt.logs import logger


class ActionDetail(BaseModel):
    name: str
    inputs: List[str]
    outputs: List[str]
    if_condition: str
    reason: str

    def get_markdown(self, indent: int = 2) -> str:
        prefix = "  " * indent
        md = f"{prefix}- {self.name}\n"
        prefix += "  "
        if self.inputs:
            md += f"{prefix}- Inputs:\n"
            for i in self.inputs:
                md += f"{prefix}  - {i}\n"
        if self.outputs:
            md += f"{prefix}- Outputs:\n"
            for i in self.outputs:
                md += f"{prefix}  - {i}\n"
        if self.if_condition:
            md += f"{prefix}- If_Condition: {self.if_condition}\n"
        return md


class ActionList(BaseModel):
    actions: List[ActionDetail]

    def get_markdown(self, indent: int = 2) -> str:
        md = ""
        for act in self.actions:
            md += act.get_markdown(indent=indent)
        return md


class ActionChainNode(BaseModel):
    pre_actions: Optional[List[str]] = None
    action_name: str
    post_actions: Optional[List[str]] = None
    if_conditions: Optional[List[str]] = None
    reason: str


class ActionOrders(BaseModel):
    detail: List[ActionChainNode] = Field(default_factory=list)

    def get_dag_list(self) -> List[str]:
        dag_list = []
        for i in self.detail:
            if not i.pre_actions:
                dag_list.append(i.action_name)

        max_try = len(self.detail)
        for i in range(0, max_try):
            for j in self.detail:
                if j.action_name in dag_list:
                    continue
                is_ready = True
                for j_pre in j.pre_actions:
                    if j_pre not in dag_list:
                        is_ready = False
                        break
                if is_ready:
                    dag_list.append(j.action_name)

        if len(dag_list) == len(self.detail):
            return dag_list
        logger.error(f"The DAG contains abnormal nodes: {self.model_dump_json()}")
        for i in self.detail:
            if i.action_name not in dag_list:
                dag_list.append(i.action_name)
        return dag_list

    def get_if_condition(self, action_name: str) -> Optional[List[str]]:
        for i in self.detail:
            if i.action_name == action_name:
                return i.if_conditions
        return None
