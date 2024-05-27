#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/29
@Author  : mashenquan
@File    : merge_data_flow.py
@Desc    : The implementation of the Chapter 2.2.17 of RFC145.
"""
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, Field

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.activity_common import (
    ActionDetail,
    ActionList,
    ActionOrders,
)
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.merge_swimlane.merge_action_dag import (
    IfStatementArgument,
)
from metagpt.actions.requirement_analysis.text_to_class import ClassCodeBlock
from metagpt.actions.requirement_analysis.use_case_common import UseCaseDetail
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    CodeParser,
    add_affix,
    concat_namespace,
    parse_json_code_block,
    remove_affix,
    split_namespace,
)


class _ClassNameList(BaseModel):
    class_names: List[str] = Field(default_factory=list)
    reason: str


class ActionClassReference(BaseModel):
    action_name: str
    input_class_names: List[str] = Field(default_factory=list)
    output_class_names: List[str] = Field(default_factory=list)
    if_condition_class_names: List[str] = Field(default_factory=list)

    def add(self, type_: str, class_name: str):
        if type_ == GraphKeyWords.If:
            lst = self.if_condition_class_names
        elif type_ == GraphKeyWords.Input:
            lst = self.input_class_names
        else:
            lst = self.output_class_names

        if class_name not in lst:
            lst.append(class_name)

    def delete(self, type_: str, class_name: str):
        if type_ == GraphKeyWords.If:
            lst = self.if_condition_class_names
        elif type_ == GraphKeyWords.Input:
            lst = self.input_class_names
        else:
            lst = self.output_class_names

        if class_name not in lst:
            return
        lst.remove(class_name)

    def get_class_names(self, exclude: Optional[List[str]] = None, type_: Optional[str] = None) -> Set[str]:
        mappings = {
            GraphKeyWords.If: set(self.if_condition_class_names),
            GraphKeyWords.Input: set(self.input_class_names),
            GraphKeyWords.Output: set(self.output_class_names),
        }
        if type_:
            return mappings.get(type_)

        exclude = exclude or []
        class_names = set()
        for k in mappings.keys():
            if k in exclude:
                continue
            class_names.update(mappings[k])
        return class_names


class UseCaseClassReferenceTable(BaseModel):
    actions: Dict[str, ActionClassReference] = Field(default_factory=dict)

    def add(self, action_name: str, type_: str, class_name: str):
        action = self.get_action(action_name)
        if not action:
            action = ActionClassReference(action_name=action_name)
        action.add(type_=type_, class_name=class_name)
        self.actions[action.action_name] = action

    def delete(self, action_name: str, type_: str, class_name: str):
        action = self.get_action(action_name)
        if not action:
            return
        action.delete(type_=type_, class_name=class_name)

    def get_action(self, action_name: str) -> Optional[ActionClassReference]:
        return self.actions.get(action_name)

    def get_class_names(self, exclude: Optional[List[str]] = None, type_: Optional[str] = None) -> Set[str]:
        exclude = exclude or []
        class_names = set()
        for i in self.actions.values():
            if i.action_name in exclude:
                continue
            names = i.get_class_names(type_=type_)
            class_names.update(names)
        return class_names


class MergeDataFlow(GraphDBAction):
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

    async def _merge_use_case(self, ns_use_case: str):
        action_orders = await self._get_action_orders(ns_use_case)
        dag_list = action_orders.get_dag_list()
        for i in dag_list:
            await self._merge_action(ns_use_case=ns_use_case, action_name=i, dag_list=dag_list)

    async def _merge_action(self, ns_use_case: str, action_name: str, dag_list: List[str]):
        # rows = await self.graph_db.select()
        await self._merge_if_condition(ns_use_case=ns_use_case, action_name=action_name)
        await self._validate_action_if_condition(ns_use_case=ns_use_case, action_name=action_name, dag_list=dag_list)
        await self._merge_action_input(ns_use_case=ns_use_case, action_name=action_name)
        await self._validate_action_input_data_flow(ns_use_case=ns_use_case, action_name=action_name, dag_list=dag_list)
        await self._merge_action_output(ns_use_case=ns_use_case, action_name=action_name)
        await self._validate_action_output_data_flow(
            ns_use_case=ns_use_case, action_name=action_name, dag_list=dag_list
        )
        # rows = await self.graph_db.select()
        pass

    async def _merge_if_condition(self, ns_use_case: str, action_name: str):
        if_conditions = await self._get_action_if_condition(action_name)
        for arg in if_conditions:
            class_list = await self._get_class_list(ns_use_case)
            class_name = await self._is_enrolled_in_if(class_list=class_list, if_condition=arg)
            class_detail = None if not class_name else class_list.get(class_name)
            if not class_detail:
                class_detail = await self._new_class_if(if_condition=arg, exists_names=list(class_list.keys()))
            # update use case class usage
            await self._update_use_case_class_usage(
                ns_use_case=ns_use_case, action_name=action_name, class_name=class_detail.name, type_=GraphKeyWords.If
            )
            # use case class 候选池
            await self.graph_db.insert(
                subject=ns_use_case,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_action_if_argument_class,
                    GraphKeyWords.Has_ + GraphKeyWords.Class,
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_action_if_argument_class, add_affix(class_detail.name)
                ),
            )
            # if condition
            await self.graph_db.insert(
                subject=concat_namespace(
                    self.context.kwargs.ns.activity_action_if_argument_class, add_affix(class_detail.name)
                ),
                predicate=concat_namespace(self.context.kwargs.ns.activity_action_if_argument_class, GraphKeyWords.Is_),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_action_if_argument_class, GraphKeyWords.Class_
                ),
            )
            await self.graph_db.insert(
                subject=concat_namespace(
                    self.context.kwargs.ns.activity_action_if_argument_class, add_affix(class_detail.name)
                ),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_action_if_argument_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_action_if_argument_class, add_affix(class_detail.model_dump_json())
                ),
            )

    async def _is_enrolled_in_if(self, class_list: Dict[str, ClassCodeBlock], if_condition: IfStatementArgument) -> str:
        prompt = (
            "## Argument:\n"
            f"- Name: {if_condition.name}\n"
            f"- Description: {if_condition.description}\n"
            f"- Original Requirement: {if_condition.context}\n"
        )
        prompt += "\n---\n"
        prompt += "## Class Definitions\n" + "\n\n".join([c.get_markdown() for c in class_list.values()])

        prompt += "\n---\n"
        prompt += 'Can a class definition be found in "Class Definitions" that matches the description and original requirements of "Argument"?'

        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "Return a markdown JSON object with:"
                '- a "result" key with boolean value true if found, otherwise false; '
                '- a "class_name" key with the class name obtained from "Class Definitions" if the class definition exists, otherwise an empty string; '
                '- a "reason" key explaining why.'
            ],
            stream=False,
        )
        json_blocks = parse_json_code_block(rsp)

        class _Data(BaseModel):
            result: bool
            class_name: str
            reason: str

        ret = _Data.model_validate_json(json_blocks[0])
        return ret.class_name

    async def _new_class_if(self, if_condition: IfStatementArgument, exists_names: List[str]) -> ClassCodeBlock:
        prompt = (
            f"- Class Name: {if_condition.name}\n"
            f"- Class Description: {if_condition.description}\n"
            f"- Context: {if_condition.context}\n"
        )
        prompt += "\n---\n"
        prompt += "## Exists Class Names\n" + "\n".join(f"- {i}" for i in exists_names)
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool that translates class descriptions into UML 2.0 classes.",
                'If a new class name conflicts with an existing class name under "Exists Class Names", rename the new class to avoid name conflict.',
                'Return each class in a JSON object in Markdown format with a "name" key for the class name, a "description" key to describe the class functionality, a "goal" key to outline the goal the class aims to achieve, a "properties" key to list the property names of the class, and a "reason" key to provide explanations.',
            ],
            stream=False,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        return ClassCodeBlock.model_validate_json(json_blocks[0])

    async def _merge_action_input(self, ns_use_case: str, action_name: str):
        action_detail = await self._get_action_detail(ns_use_case=ns_use_case, action_name=action_name)
        if not action_detail or not action_detail.inputs:
            return
        for i in action_detail.inputs:
            class_list = await self._get_class_list(ns_use_case)
            class_name = await self._is_enrolled_in_op(
                class_list=class_list, action_name=action_detail.name, input_name=i
            )
            class_detail = None if not class_name else class_list.get(class_name)
            if not class_detail:
                class_detail = await self._new_class_op(
                    action_name=action_detail.name, input_name=i, exists_names=list(class_list.keys())
                )
            # use case class候选池
            await self.graph_db.insert(
                subject=ns_use_case,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_input_class, GraphKeyWords.Has_ + GraphKeyWords.Class
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_input_class, add_affix(class_detail.name)),
            )
            # input class 候选池
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_input_class, add_affix(class_detail.name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_input_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_input_class, add_affix(class_detail.model_dump_json())
                ),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_input_class, add_affix(class_detail.name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_input_class, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_input_class, GraphKeyWords.Class_),
            )

    async def _is_enrolled_in_op(self, class_list: Dict[str, ClassCodeBlock], action_name: str, input_name: str) -> str:
        prompt = "## Argument:\n" f"- Description: {input_name}\n" f"- Usage: {action_name}\n"
        prompt += "\n---\n"
        prompt += "## Class Definitions\n" + "\n\n".join([c.get_markdown() for c in class_list.values()])
        prompt += "\n---\n"

        prompt += 'Can a class definition be found in "Class Definitions" that matches the description and original requirements of "Argument"?'

        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                'The "Usage" of "Argument" describes the scenarios in which this parameter is used, which can aid in understanding the content of the "Description" of "Argument".',
                "Return a markdown JSON object with:"
                '- a "result" key with boolean value true if found, otherwise false; '
                '- a "class_name" key with the class name obtained from "Class Definitions" if the class definition exists, otherwise an empty string; '
                '- a "reason" key explaining why',
            ],
            stream=False,
        )
        json_block = CodeParser.parse_code(text=rsp, lang="json", block="")
        if not json_block or json_block == rsp:
            return ""

        class _Data(BaseModel):
            result: bool
            class_name: str
            reason: str

        ret = _Data.model_validate_json(json_block)
        return ret.class_name

    async def _new_class_op(self, action_name: str, input_name: str, exists_names: List[str]) -> ClassCodeBlock:
        prompt = f"- Class Description: {input_name}\n" f"- Usage: {action_name}\n"
        prompt += "\n---\n"
        prompt += "## Exists Class Names\n" + "\n".join(f"- {i}" for i in exists_names)
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                "You are a tool that translates class descriptions into UML 2.0 classes.",
                'The "Usage" describes the scenarios in which this parameter is used, which can aid in understanding the content of the "Class Description".',
                'If a new class name conflicts with an existing class name under "Exists Class Names", rename the new class to avoid name conflict.',
                "Return each class in a JSON object in Markdown format with:"
                '- a "name" key for the semantic class name with contextual information; '
                '- a "description" key to describe the class functionality;'
                '- a "goal" key to outline the goal the class aims to achieve; '
                '- a "properties" key to list the names of possible properties;'
                '- a "reason" key to provide explanations.',
            ],
            stream=False,
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        return ClassCodeBlock.model_validate_json(json_blocks[0])

    async def _merge_action_output(self, ns_use_case: str, action_name: str):
        action_detail = await self._get_action_detail(ns_use_case=ns_use_case, action_name=action_name)
        if not action_detail or not action_detail.outputs:
            return
        for i in action_detail.outputs:
            class_list = await self._get_class_list(ns_use_case)
            class_name = await self._is_enrolled_in_op(
                class_list=class_list, action_name=action_detail.name, input_name=i
            )
            class_detail = None if not class_name else class_list.get(class_name)
            if not class_detail:
                class_detail = await self._new_class_op(
                    action_name=action_detail.name, input_name=i, exists_names=list(class_list.keys())
                )

            # use case候选池
            await self.graph_db.insert(
                subject=ns_use_case,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_output_class, GraphKeyWords.Has_ + GraphKeyWords.Class
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_output_class, add_affix(class_detail.name)),
            )
            # output class
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_output_class, add_affix(class_detail.name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_output_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_output_class, add_affix(class_detail.model_dump_json())
                ),
            )
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_output_class, add_affix(class_detail.name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_output_class, GraphKeyWords.Is_),
                object_=concat_namespace(self.context.kwargs.ns.activity_output_class, GraphKeyWords.Class_),
            )

    async def _get_class_list(self, ns_use_case: str) -> Dict[str, ClassCodeBlock]:
        classes = await self._get_ns_input_class_details(ns_use_case)
        outputs = await self._get_ns_output_class_details(ns_use_case)
        classes.update(outputs)
        if_args = await self._get_ns_if_condition_class_details(ns_use_case)
        classes.update(if_args)
        return classes

    async def _get_ns_input_class_details(self, ns_use_case: str) -> Dict[str, ClassCodeBlock]:
        ns_input_class_names = await self._get_ns_input_class_names(ns_use_case)
        class_details = {}
        for i in ns_input_class_names:
            if i in class_details:
                continue
            rows = await self.graph_db.select(
                subject=i,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_input_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
            )
            json_data = remove_affix(split_namespace(rows[0].object_)[-1])
            class_ = ClassCodeBlock.model_validate_json(json_data)
            class_details[class_.name] = class_
        return class_details

    async def _get_ns_output_class_details(self, ns_use_case: str) -> Dict[str, ClassCodeBlock]:
        ns_output_class_names = await self._get_ns_output_class_names(ns_use_case)
        class_details = {}
        for i in ns_output_class_names:
            if i in class_details:
                continue
            rows = await self.graph_db.select(
                subject=i,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_output_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
            )
            json_data = remove_affix(split_namespace(rows[0].object_)[-1])
            class_ = ClassCodeBlock.model_validate_json(json_data)
            class_details[class_.name] = class_
        return class_details

    async def _get_ns_if_condition_class_details(self, ns_use_case: str) -> Dict[str, ClassCodeBlock]:
        ns_if_condition_class_names = await self._get_ns_if_condition_class_names(ns_use_case)
        class_details = {}
        for i in ns_if_condition_class_names:
            if i in class_details:
                continue
            rows = await self.graph_db.select(
                subject=i,
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_action_if_argument_class, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
            )
            json_data = remove_affix(split_namespace(rows[0].object_)[-1])
            class_ = ClassCodeBlock.model_validate_json(json_data)
            class_details[class_.name] = class_
        return class_details

    async def _get_ns_if_condition_class_names(self, ns_use_case):
        rows = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_action_if_argument_class, GraphKeyWords.Has_ + GraphKeyWords.Class
            ),
        )
        return [r.object_ for r in rows]

    async def _get_original_requirement(self) -> str:
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.OriginalRequirement),
            predicate=concat_namespace(self.context.kwargs.ns.namespace, GraphKeyWords.Is_),
        )
        original_requirement = remove_affix(split_namespace(rows[0].object_)[-1])
        return original_requirement

    async def _get_use_case_detail(self, ns_use_case: str) -> UseCaseDetail:
        rows = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(self.context.kwargs.ns.use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail),
        )
        json_data = remove_affix(split_namespace(rows[0].object_)[-1])
        use_case_detail = UseCaseDetail.model_validate_json(json_data)
        return use_case_detail

    async def _get_action_detail(self, ns_use_case: str, action_name: str) -> Optional[ActionDetail]:
        actions = await self._get_action_list(ns_use_case)
        for i in actions.actions:
            if i.name == action_name:
                return i
        return None

    async def _get_action_list(self, ns_use_case: str) -> ActionList:
        rows = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_action, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        json_data = remove_affix(split_namespace(rows[0].object_)[-1])
        return ActionList.model_validate_json(json_data)

    async def _get_action_orders(self, ns_use_case) -> ActionOrders:
        rows = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_control_flow, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        json_data = remove_affix(split_namespace(rows[0].object_)[-1])
        return ActionOrders.model_validate_json(json_data)

    async def _get_ns_input_class_names(self, ns_use_case) -> List[str]:
        rows = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_input_class, GraphKeyWords.Has_ + GraphKeyWords.Class
            ),
        )
        return [r.object_ for r in rows]

    async def _get_ns_output_class_names(self, ns_use_case) -> List[str]:
        rows = await self.graph_db.select(
            subject=ns_use_case,
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_output_class, GraphKeyWords.Has_ + GraphKeyWords.Class
            ),
        )
        return [r.object_ for r in rows]

    async def _get_action_if_condition(self, action_name: str) -> List[IfStatementArgument]:
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.activity_control_flow_action, add_affix(action_name)),
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_control_flow_action_if_argument,
                GraphKeyWords.Has_ + GraphKeyWords.IfCondition + GraphKeyWords.Argument,
            ),
        )
        ns_arg_names = {r.object_ for r in rows}
        if_conditions = []
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_control_flow_action_if_argument,
                GraphKeyWords.Has_ + GraphKeyWords.Detail,
            ),
        )
        for r in rows:
            if r.subject in ns_arg_names:
                json_data = remove_affix(split_namespace(r.object_)[-1])
                arg = IfStatementArgument.model_validate_json(json_data)
                if_conditions.append(arg)
        return if_conditions

    async def _validate_action_if_condition(self, ns_use_case: str, action_name: str, dag_list: List[str]):
        # 检查if-condition是否在上游出现
        # 如果未出现过:
        # 要么上游某个action的output缺失，要么当前if-condition时序错误
        class_usage = await self._get_use_case_class_usage(ns_use_case)
        action = class_usage.get_action(action_name)
        if not action or not action.if_condition_class_names:
            return

        ix = dag_list.index(action_name)
        available_classes = class_usage.get_class_names(exclude=dag_list[ix:])
        err_if_conditions = []
        for i in action.if_condition_class_names:
            if i in available_classes:
                continue
            err_if_conditions.append(i)
        if not err_if_conditions:
            return
        await self._fixbug_action_if_conditions(err_if_conditions, ns_use_case, action_name)

    async def _fixbug_action_if_conditions(self, err_if_conditions: List[str], ns_use_case: str, action_name: str):
        ordered_actions = await self._get_ordered_action_details(ns_use_case)
        done = set()
        for class_name in err_if_conditions:
            new_action_name = await self._search_outputted_action(
                class_name=class_name, ordered_actions=ordered_actions, ns_use_case=ns_use_case, action_name=action_name
            )
            # 如果new_action_name无效,说明这个参数依赖外部提供
            if not new_action_name:
                continue

            idx = {v.name: i for i, v in enumerate(ordered_actions) if v.name in {action_name, new_action_name}}
            if idx[new_action_name] < idx[action_name]:
                # new_action_name新增output 参数
                await self._update_use_case_class_usage(
                    ns_use_case=ns_use_case,
                    action_name=new_action_name,
                    class_name=class_name,
                    type_=GraphKeyWords.Output,
                )
            else:
                # if condition先于new_action_name出现，则说明if condition是错的
                await self._update_use_case_class_usage(
                    ns_use_case=ns_use_case,
                    action_name=action_name,
                    class_name=class_name,
                    type_=GraphKeyWords.If,
                    is_delete=True,
                )
                await self._update_use_case_class_usage(
                    ns_use_case=ns_use_case,
                    action_name=new_action_name,
                    class_name=class_name,
                    type_=GraphKeyWords.Output,
                )
            done.add(class_name)

    async def _search_outputted_action(
        self, class_name: str, ordered_actions: List[ActionDetail], ns_use_case: str, action_name: str
    ) -> str:
        use_case_detail = await self._get_use_case_detail(ns_use_case)
        class_list = await self._get_class_list(ns_use_case)
        class_detail = class_list[class_name]
        prompt = "## Class\n" + class_detail.get_markdown()
        prompt += "\n---\n"
        prompt += f"## Use Case\n- Description: {use_case_detail.description}\n- Goal: {use_case_detail.goal}\n"
        prompt += "- Action List:\n" + "".join([f"  {i}. {v.name}\n" for i, v in enumerate(ordered_actions)])
        prompt += f"  {len(ordered_actions)}. None of the above\n"
        rsp = await self.llm.aask(
            msg=prompt,
            system_msgs=[
                f'Which action in the "Action List" of the "Use Case" will output the "{class_name}" class?',
                "Return a markdown JSON object with:"
                f'- an "idx" key containing the integer value of index of the name of the action in the "Action List" that will output the "{class_name}" class; '
                '- a "reason" key explaining why.',
            ],
            stream=False,
        )
        json_blocks = parse_json_code_block(rsp)

        class _Data(BaseModel):
            idx: int
            reason: str

        data = _Data.model_validate_json(json_blocks[0])
        if data.idx == len(ordered_actions):
            return ""
        return ordered_actions[data.idx].name

    async def _validate_action_input_data_flow(self, ns_use_case: str, action_name: str, dag_list: List[str]):
        # 暂时没有规则可查
        pass

    async def _validate_action_output_data_flow(self, ns_use_case: str, action_name: str, dag_list: List[str]):
        # 检查output是否在上游出现
        # 如果在上游出现：说明时序错误
        # rows = await self.graph_db.select()
        class_usage = await self._get_use_case_class_usage(ns_use_case)
        ix = dag_list.index(action_name)
        available_classes = class_usage.get_class_names(exclude=dag_list[ix:])
        action = class_usage.get_action(action_name)
        if not action:
            return
        available_classes.update(action.get_class_names(exclude=[GraphKeyWords.Output]))
        err_outputs = []
        for i in action.output_class_names:
            if i in available_classes:
                err_outputs.append(i)
        if not err_outputs:
            return
        await self._fixbug_action_output(err_outputs, ns_use_case, action_name)

    async def _fixbug_action_output(self, err_outputs: List[str], ns_use_case: str, action_name: str):
        ordered_actions = await self._get_ordered_action_details(ns_use_case)
        done = set()
        for class_name in err_outputs:
            new_action_name = await self._search_outputted_action(
                class_name=class_name, ordered_actions=ordered_actions, ns_use_case=ns_use_case, action_name=action_name
            )
            if new_action_name != action_name:
                await self._update_use_case_class_usage(
                    ns_use_case=ns_use_case,
                    action_name=action_name,
                    class_name=class_name,
                    type_=GraphKeyWords.Output,
                    is_delete=True,
                )
            # new_action_name无效，说明class_name不是当前action_name的输出,需要将class_name移到new_action_name
            if new_action_name:
                await self._update_use_case_class_usage(
                    ns_use_case=ns_use_case,
                    action_name=new_action_name,
                    class_name=class_name,
                    type_=GraphKeyWords.Output,
                )
            done.add(class_name)
        for i in err_outputs:
            if i in done:
                continue
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_swimlane_action, add_affix(action_name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_action_output_class,
                    GraphKeyWords.Missing_ + GraphKeyWords.Has_ + GraphKeyWords.Output + GraphKeyWords.Class,
                ),
                object_=concat_namespace(self.context.kwargs.ns.activity_action_output_class, add_affix(i)),
            )

    async def _get_ordered_action_details(self, ns_use_case: str) -> List[ActionDetail]:
        action_orders = await self._get_action_orders(ns_use_case)
        dag_list = action_orders.get_dag_list()
        ordered_action_details = []
        for i in dag_list:
            detail = await self._get_action_detail(ns_use_case=ns_use_case, action_name=i)
            ordered_action_details.append(detail)
        return ordered_action_details

    async def _update_use_case_class_usage(
        self, ns_use_case: str, action_name: str, class_name: str, type_: str, is_delete: bool = False
    ):
        use_case_name = remove_affix(split_namespace(ns_use_case)[-1])
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.activity_class_usage, add_affix(use_case_name)),
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_class_usage, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        if rows:
            json_data = remove_affix(split_namespace(rows[0].object_)[-1])
            await self.graph_db.delete(
                subject=concat_namespace(self.context.kwargs.ns.activity_class_usage, add_affix(use_case_name)),
                predicate=concat_namespace(
                    self.context.kwargs.ns.activity_class_usage, GraphKeyWords.Has_ + GraphKeyWords.Detail
                ),
                object_=rows[0].object_,
            )
            class_refs = UseCaseClassReferenceTable.model_validate_json(json_data)
        else:
            await self.graph_db.insert(
                subject=concat_namespace(self.context.kwargs.ns.activity_class_usage, add_affix(use_case_name)),
                predicate=concat_namespace(self.context.kwargs.ns.activity_class_usage, GraphKeyWords.Is_),
                object_=concat_namespace(
                    self.context.kwargs.ns.activity_class_usage, GraphKeyWords.Class_ + GraphKeyWords.Reference
                ),
            )
            class_refs = UseCaseClassReferenceTable()
        if not is_delete:
            class_refs.add(action_name=action_name, type_=type_, class_name=class_name)
        else:
            class_refs.delete(action_name=action_name, type_=type_, class_name=class_name)
        await self.graph_db.insert(
            subject=concat_namespace(self.context.kwargs.ns.activity_class_usage, add_affix(use_case_name)),
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_class_usage, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
            object_=concat_namespace(
                self.context.kwargs.ns.activity_class_usage, add_affix(class_refs.model_dump_json())
            ),
        )

    async def _get_use_case_class_usage(self, ns_use_case: str) -> UseCaseClassReferenceTable:
        use_case_name = remove_affix(split_namespace(ns_use_case)[-1])
        rows = await self.graph_db.select(
            subject=concat_namespace(self.context.kwargs.ns.activity_class_usage, add_affix(use_case_name)),
            predicate=concat_namespace(
                self.context.kwargs.ns.activity_class_usage, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
        )
        if not rows:
            return UseCaseClassReferenceTable()
        json_data = remove_affix(split_namespace(rows[0].object_)[-1])
        return UseCaseClassReferenceTable.model_validate_json(json_data)
