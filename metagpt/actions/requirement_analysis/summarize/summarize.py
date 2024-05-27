#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : summarize.py
@Desc    : Drawing conclusions based on inference.
        plantuml Guide: https://plantuml.com/en/guide, https://plantuml.com/zh/activity-diagram-beta,
        online plantuml tool: https://plantuml-editor.kkeisuke.com/,
        online markdown tool: https://markdown.lovejade.cn/

```plantuml
@startuml

left to right direction

actor User
actor A
actor system

package system {
  usecase "Eat Food" as UC1
  usecase "Pay for Food" as UC2
  usecase "Drink" as UC3
  usecase "Review" as UC4
}

User -- UC1 : extends
User -- UC2 : extends

@enduml
```
"""
from typing import Dict, List, Optional

from pydantic import Field

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.activity_common import ActionOrders
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.merge_swimlane.merge_data_flow import (
    ActionClassReference,
    UseCaseClassReferenceTable,
)
from metagpt.actions.requirement_analysis.text_to_class import ClassCodeBlock
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import concat_namespace, remove_affix, split_namespace


class Summarize(GraphDBAction):
    actors: List[str] = Field(default_factory=list)
    systems: List[str] = Field(default_factory=list)
    use_cases: List[str] = Field(default_factory=list)
    error_infos: List = Field(default_factory=list)

    async def run(self, with_messages: Message = None):
        await self.load_graph_db()

        await self._create_user_requirement()
        await self._create_use_case_view()
        await self._create_activity_view()
        await self._create_class_view()
        await self._create_external_class_view()

    async def _create_user_requirement(self) -> str:
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.Is_),
        )

        md = "```text\n"
        md += "\n".join([remove_affix(split_namespace(r.object_)[-1]) for r in rows])
        md += "\n```\n"
        await self.context.repo.resources.requirement_analysis.save("user_requirement.md", content=md)

        return md

    async def _create_use_case_view(self) -> str:
        md = "```plantuml\n@startuml\n\nleft to right direction\n\n"
        self.actors = await self._get_actors()
        for i in self.actors:
            md += f'actor "{i}"\n'

        md += "rectangle system {\n"
        self.systems = await self._get_systems()
        for i in self.systems:
            md += f'  actor "{i}"\n'
        self.use_cases = await self._get_use_cases()
        for i in self.use_cases:
            md += f'  usecase "{i}"\n'
        md += "}\n"

        distinct = set()
        participants = self.actors + self.systems
        for i in participants:
            use_cases = await self._get_use_cases(actor=i)
            if not use_cases:
                self.error_infos.insert((f'actor "{i}"', "Unused"))
                continue
            for uc in use_cases:
                association = f'"{i}" -- "{uc}"\n'
                if association in distinct:
                    continue
                md += association
                distinct.add(association)

        md += "\n@enduml\n```"

        await self.context.repo.resources.requirement_analysis.save("use_case.md", content=md)
        return md

    async def _create_activity_view(self) -> str:
        swimlanes = await self._get_swimlanes()
        action_swimlane_mapping = await self._get_action_swimlane_mapping()
        action_order_list = await self._get_action_order_list()
        class_reference_list = await self._get_class_reference_list()

        md = "```plantuml\n@startuml\n"
        colors = ["#eeffee|", ""]
        for aol in action_order_list:
            dag = aol.get_dag_list()
            for i, action_name in enumerate(dag):
                swimlane = action_swimlane_mapping.get(action_name)
                if swimlane:
                    swimlane_ix = swimlanes.index(swimlane)
                    color = colors[swimlane_ix % 2]
                else:
                    swimlane = "<ERROR>"
                    color = "#red|"
                md += f"|{color}{swimlane}|\n"
                if i == 0:
                    md += "start\n"
                action_detail = class_reference_list.get(action_name)
                if not action_detail:
                    logger.warning(f"{action_name} dose not exists")
                    md += f':"{action_name}"();\n'
                    continue
                operation = (
                    f'"{action_detail.action_name}"('
                    + ",".join([f'"{i}"' for i in action_detail.input_class_names])
                    + ")"
                )
                if action_detail.output_class_names:
                    operation += " return (" + ",".join([f'"{i}"' for i in action_detail.output_class_names]) + ")"
                operation += ""
                if action_detail and action_detail.if_condition_class_names:
                    md += (
                        "if (" + ",".join([f'"{i}"' for i in action_detail.if_condition_class_names]) + ") then (yes)\n"
                    )
                    md += f":{operation};\n"
                    md += "else\nend\nendif\n"
                else:
                    md += f":{operation};\n"
        md += "end\n@enduml\n```\n"

        await self.context.repo.resources.requirement_analysis.save("activity.md", content=md)
        return md

    async def _create_class_view(self, class_names: List[str] = None, filename="class.md") -> str:
        classes = {}
        input_rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_input_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
            )
        )
        output_rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_output_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
            )
        )
        if_condition_rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_action_if_argument_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        rows = input_rows + output_rows + if_condition_rows
        for r in rows:
            json_data = remove_affix(split_namespace(r.object_)[-1])
            class_ = ClassCodeBlock.model_validate_json(json_data)
            classes[class_.name] = class_

        md = "```plantuml\n@startuml\n"
        for class_ in classes.values():
            if class_names and class_.name not in class_names:
                continue
            md += f'class "{class_.name}" ' + "{\n"
            md += "".join([f"\t{i}\n" for i in class_.properties])
            md += "}\n"

        md += "@enduml\n```\n"

        await self.context.repo.resources.requirement_analysis.save(filename, content=md)
        return md

    async def _create_external_class_view(self) -> str:
        invalid = set()
        valid = set()
        action_order_list = await self._get_action_order_list()
        class_reference_list = await self._get_class_reference_list()
        for aol in action_order_list:
            dag = aol.get_dag_list()
            for action_name in dag:
                action_detail = class_reference_list.get(action_name)
                if not action_detail:
                    continue
                for i in action_detail.if_condition_class_names:
                    if i not in valid:
                        invalid.add(i)
                for i in action_detail.input_class_names:
                    if i not in valid:
                        invalid.add(i)
                for i in action_detail.output_class_names:
                    valid.add(i)

        md = await self._create_class_view(list(invalid), filename="external_class.md")
        return md

    async def _get_actors(self) -> List[str]:
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Actor_),
        )
        return [remove_affix(split_namespace(r.subject)[-1]) for r in rows]

    async def _get_systems(self) -> List[str]:
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.System_),
        )
        return [remove_affix(split_namespace(r.subject)[-1]) for r in rows]

    async def _get_use_cases(self, actor: Optional[str] = None) -> List[str]:
        if not actor:
            rows = await self.graph_db.select(
                predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.UseCase_),
            )
            return [remove_affix(split_namespace(i.subject)[-1]) for i in rows]
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Associate_)
        )
        use_cases = set()
        for r in rows:
            subject = remove_affix(split_namespace(r.subject)[-1])
            object_ = remove_affix(split_namespace(r.object_)[-1])
            if subject == actor:
                use_cases.add(object_)
            else:
                use_cases.add(subject)
        return list(use_cases)

    async def _get_swimlanes(self):
        """Get a list of swimlane names"""
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.activity_swimlane, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.activity_swimlane, GraphKeyWords.Swimlane_),
        )
        return [remove_affix(split_namespace(r.subject)[-1]) for r in rows]

    async def _get_action_swimlane_mapping(self) -> Dict[str, str]:
        """

        Returns:
            Return a dict of action_name to swimlane name mapping.
        """
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, GraphKeyWords.Do_),
        )
        mapping = {}
        for r in rows:
            swimlane = remove_affix(split_namespace(r.subject)[-1])
            action_name = remove_affix(split_namespace(r.object_)[-1])
            mapping[action_name] = swimlane
        return mapping

    async def _get_action_order_list(self) -> List[ActionOrders]:
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_control_flow, GraphKeyWords.Has_ + GraphKeyWords.Detail
            )
        )
        return [ActionOrders.model_validate_json(remove_affix(split_namespace(r.object_)[-1])) for r in rows]

    async def _get_class_reference_list(self) -> Dict[str, ActionClassReference]:
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_class_usage, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        refs = {}
        for r in rows:
            v = UseCaseClassReferenceTable.model_validate_json(remove_affix(split_namespace(r.object_)[-1]))
            refs.update(v.actions)
        return refs
