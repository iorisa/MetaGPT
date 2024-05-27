#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/5/24
@Author  : mashenquan
@File    : write_system_design.py
@Desc    : Write a design document in the format used by the software company team.
"""
import json
from typing import List

from pydantic import BaseModel

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.schema import Document, Message
from metagpt.utils.common import (
    CodeParser,
    awrite,
    concat_namespace,
    remove_affix,
    split_namespace,
)


class WriteSystemDesign(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()

        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.System_),
        )
        actor_names = [remove_affix(split_namespace(r.subject)[-1]) for r in rows]
        systems = await self._select_system(actor_names)
        await self._write_system_design(systems)

    async def _select_system(self, actor_names: List[str]) -> List[str]:
        activity_diagram = await self.context.repo.resources.requirement_analysis.get("activity.md")
        requirement = await self.context.repo.requirement

        prompt = f"## Activity Diagram\n{activity_diagram.content}\n"
        prompt += f"## User Requirement\n{requirement.content}\n"

        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                'Based on the "Activity Diagram" and "User Requirement", which of the following systems following is currently to be developed? Why?\n'
                "".join([f'{i}. "{v}"\n' for i, v in enumerate(actor_names)]),
                "Return a markdown JSON object with:\n"
                '- a "system" key containing the string list object of names currently to be developed;\n'
                '- a "references" key containing the string list of strings of evidence references from the "User Requirement" section of your judgement;\n'
                '- a "reason" key explaining why;\n',
            ],
        )
        json_block = CodeParser.parse_code(text=rsp, lang="json", block="")

        class _JsonData(BaseModel):
            system: List[str]
            references: List[str]
            reason: str

        data = _JsonData.model_validate_json(json_block)
        return data.system

    async def _write_system_design(self, systems: List[str]):
        activity_diagram = await self.context.repo.resources.requirement_analysis.get("activity.md")
        requirement = await self.context.repo.requirement

        prompt = f"## Activity Diagram\n{activity_diagram.content}\n"
        prompt += f"## User Requirement\n{requirement.content}\n"
        prompt += "## System To Develop\n" + "".join([f"- {i}\n" for i in systems])

        sequence_diagram = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                'According to "User Requirement" and "Activity Diagram", generate a plantuml sequence diagram for the system to be developed in "System To Develop".'
            ],
        )
        class_diagram = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                'According to "User Requirement" and "Activity Diagram", generate a plantuml class diagram for the system to be developed in "System To Develop".'
            ],
        )

        prompt += f"## Sequence Diagram\n{sequence_diagram}\n"
        prompt += f"## Class Diagram\n{class_diagram}\n"
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "Return a markdown JSON object with:\n"
                '- an "Implementation approach" key containing the natural text about implementation approach according to the "Activity Diagram", "Sequence Diagram", "Class Diagram" and "User Requirement";\n'
                '- a "File list" key containing the string list of file names to code;\n'
                '- a "Language" key containing the program language;\n'
            ],
        )

        json_data = CodeParser.parse_code(text=rsp, lang="json", block="")
        m = json.loads(json_data)
        m["Program call flow"] = sequence_diagram
        m["Data structures and interfaces"] = class_diagram
        json_data = json.dumps(m)
        await self.context.repo.docs.system_design.save(filename="design.json", content=json_data)
        await self.context.repo.resources.system_design.save_pdf(doc=Document(filename="design", content=json_data))
        await awrite(filename=self.context.repo.resources.data_api_design.workdir / "design.md", data=class_diagram)
        await awrite(filename=self.context.repo.resources.seq_flow.workdir / "design.md", data=sequence_diagram)
