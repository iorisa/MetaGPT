#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : text_to_class.py
@Desc    : Tools for the implementation of RFC145. https://deepwisdom.feishu.cn/docx/VhRCdcfQQoIlaJxWvyLcMDP9nbg
"""

from typing import List, Optional

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.logs import logger
from metagpt.utils.common import general_after_log, parse_json_code_block


class ClassCodeBlock(BaseModel):
    name: str
    description: str
    goal: str
    properties: List[str]
    reason: str

    def get_markdown(self, indent=0):
        prefix = "  " * indent
        md = prefix + f"- {self.name}\n"
        md += prefix + f"  - Description: {self.description}\n"
        md += prefix + f"  - Goal: {self.goal}\n"
        if not self.properties:
            return md
        md += prefix + "  - Properties:\n"
        for i in self.properties:
            md += prefix + f"    - {i}\n"
        return md


class ParameterItem(BaseModel):
    name: str
    description: str
    reason: str


class ParameterList(BaseModel):
    inputs: Optional[List[ParameterItem]] = None
    outputs: Optional[List[ParameterItem]] = None


@retry(
    wait=wait_random_exponential(min=1, max=20),
    stop=stop_after_attempt(6),
    after=general_after_log(logger),
)
async def text_to_class(parameter_list_json: str, llm) -> List[ClassCodeBlock]:
    parameters = ParameterList.model_validate_json(parameter_list_json)
    descriptions = []
    if parameters.inputs:
        for i in parameters.inputs:
            v = f"{len(descriptions) + 1}. Class Name: {i.name}\nClass Description: {i.description}\n"
            descriptions.append(v)
    if parameters.outputs:
        for o in parameters.outputs:
            v = f"{len(descriptions) + 1}. Class Name: {o.name}\nClass Description: {o.description}\n"
            descriptions.append(v)
    prompt = "\n---\n".join(descriptions)
    rsp = await llm.aask(
        msg=prompt,
        system_msgs=[
            "You are a tool that translates class descriptions into UML 2.0 classes.",
            'Return each class in a JSON object in Markdown format with a "name" key for the class name, a "description" key to describe the class functionality, a "goal" key to outline the goal the class aims to achieve, a "properties" key to list the property names of the class, and a "reason" key to provide explanations.',
        ],
        stream=False,
    )
    logger.info(rsp)
    json_blocks = parse_json_code_block(rsp)

    return [ClassCodeBlock.model_validate_json(block) for block in json_blocks]
