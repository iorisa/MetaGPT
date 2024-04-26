#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/29
@Author  : mashenquan
@File    : action_merge_swimlane.py
@Desc    : The implementation of the Chapter 2.2.15 of RFC145.
"""
from typing import List

from pydantic import BaseModel

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.activity.enrich_use_case import (
    ActivityEnrichUseCase,
)
from metagpt.actions.requirement_analysis.activity_common import ActionOrders
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    add_affix,
    concat_namespace,
    parse_json_code_block,
    remove_affix,
    split_namespace,
)


class SwimlaneAction(BaseModel):
    action_name: str
    actor: str
    reason: str


class SwimlaneActions(BaseModel):
    use_case: str
    details: List[SwimlaneAction]


class ActionMergeSwimlane(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()
        rows = await self.graph_db.select(
            predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Is_),
            object_=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.UseCase_),
        )
        for r in rows:
            await self._merge_use_case(r.subject)

        await self.graph_db.save()
        # rows = await self.graph_db.select()
        return Message(content="", cause_by=self)

    async def _merge_use_case(self, ns_use_case):
        rows = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        json_data = remove_affix(split_namespace(rows[0].object_)[-1])
        activity_use_case_detail = ActivityEnrichUseCase.model_validate_json(json_data)
        rows = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_control_flow, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        json_data = remove_affix(split_namespace(rows[0].object_)[-1])
        action_orders = ActionOrders.model_validate_json(json_data)
        participants = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Associate_),
        )
        actors = []
        systems = []
        for p in participants:
            rows = await self.graph_db.select(
                subject=p.object_,
                predicate=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_actor, GraphKeyWords.System_),
            )
            if rows:
                systems.append(p)
            else:
                actors.append(p)

        # TODO: 把activity_swimlane_namespace进一步拆分成activity_swimlane_actor_namespace, activity_swimlane_action_namespace等等
        for p in participants:
            affix_actor = split_namespace(p.object_)[-1]
            # Use Case 与 Activity间的关联关系
            await self.graph_db.insert(
                subject=p.object_,
                predicate=concat_namespace(self.context.kwargs.ns.activity_swimlane, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_swimlane, affix_actor),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_swimlane, affix_actor),
                predicate=concat_namespace(self.context.kwargs.ns.activity_swimlane, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_swimlane, GraphKeyWords.Swimlane_),
            )

        swimlane_actions = await self._match(
            use_case=remove_affix(split_namespace(ns_use_case)[-1]),
            use_case_detail=activity_use_case_detail,
            action_orders=action_orders,
            systems=systems,
            actors=actors,
        )
        await self.graph_db.insert(
            subject=concat_namespace(self.context.kwargs.ns.use_case, add_affix(swimlane_actions.use_case)),
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_swimlane_action_list, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
            object_=concat_namespace(
                self.context.kwargs.ns.activity_swimlane_action_list, add_affix(swimlane_actions.model_dump_json())
            ),
        )
        for i in swimlane_actions.details:
            # Position in Swimlane
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_swimlane, add_affix(i.actor)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, GraphKeyWords.Do_),
                object_=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, add_affix(i.action_name)),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, add_affix(i.action_name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, GraphKeyWords.Action),
            )
            # 理由
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, add_affix(i.action_name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_swimlane_action, GraphKeyWords.Has_ + GraphKeyWords.Reason
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, add_affix(i.reason)),
            )

    async def _match(self, use_case, use_case_detail, action_orders, systems, actors) -> SwimlaneActions:
        context = {}
        use_case_part = f"- Use Case Name: {use_case}\n"
        use_case_part += "- Use Case Description\n"
        for i in use_case_detail.references:
            use_case_part += f"  - {i}\n"
        use_case_part += "- Use Case Inputs\n"
        for i in use_case_detail.inputs:
            use_case_part += f"  - {i}\n"
        use_case_part += "- Use Case Outputs\n"
        for i in use_case_detail.outputs:
            use_case_part += f"  - {i}\n"
        use_case_part += "- Use Case actions\n"
        for i in use_case_detail.actions:
            use_case_part += f"  - {i}\n"
        context["Use Case"] = use_case_part

        action_orders_part = ""
        for i in action_orders.detail:
            action_orders_part += f"- Action: {i.action_name}\n"
            action_orders_part += "  - Pre-action Name:\n"
            for j in i.pre_actions or []:
                action_orders_part += f"    - {j}\n"
            action_orders_part += "  - Post-action Name:\n"
            for j in i.post_actions or []:
                action_orders_part += f"    - {j}\n"
            action_orders_part += "  - If-condition to call this action:\n"
            for j in i.if_conditions or []:
                action_orders_part += f"  - {j}\n"
        context["Action Orders"] = action_orders_part

        systems_part = ""
        for i in systems:
            name = remove_affix(split_namespace(i.object_)[-1])
            systems_part += f"- {name}\n"
        context["Use Case System Alias"] = systems_part

        actors_part = ""
        for i in actors:
            name = remove_affix(split_namespace(i.object_)[-1])
            actors_part += f"- {name}\n"
        context["Use Case Actors"] = actors_part

        prompt = "\n---\n".join([f"## {k}\n{v}\n" for k, v in context.items()])
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool to create UML 2.0 activity diagram.",
                "Choose an actor or system alias for each action to identify its respective executor.",
                "Return a JSON object in Markdown format with the following structure:\n"
                "- A `use_case` key containing the name of the use case.\n"
                "- A `details` key containing a list of objects. Each object should have the following keys:\n"
                "  - `action_name`: representing the name of the action.\n"
                "  - `actor`: representing the actor or system alias who executes the action.\n"
                "  - `reason`: explaining the rationale behind the matching of action name and actor.\n",
            ],
            stream=False,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        return SwimlaneActions.model_validate_json(json_blocks[0])
