#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/6
@Author  : mashenquan
@File    : namespaces.py
@Desc    : The management all namespaces used in RFC145.
"""
from pydantic import BaseModel

from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.utils.common import concat_namespace


class Namespaces(BaseModel):
    namespace: str

    @property
    def use_case(self):
        return concat_namespace(self.namespace, GraphKeyWords.UseCase, delimiter="_")

    @property
    def activity_use_case(self):
        return concat_namespace(self.namespace, GraphKeyWords.Activity, GraphKeyWords.UseCase, delimiter="_")

    @property
    def activity_input(self):
        return concat_namespace(self.namespace, GraphKeyWords.Activity, GraphKeyWords.Input, delimiter="_")

    @property
    def activity_output(self):
        return concat_namespace(self.namespace, GraphKeyWords.Activity, GraphKeyWords.Output, delimiter="_")

    @property
    def activity_action(self):
        return concat_namespace(self.namespace, GraphKeyWords.Activity, GraphKeyWords.Action, delimiter="_")

    @property
    def activity_action_input(self):
        return concat_namespace(self.activity_action, GraphKeyWords.Input, delimiter="_")

    @property
    def activity_action_output(self):
        return concat_namespace(self.activity_action, GraphKeyWords.Output, delimiter="_")

    @property
    def activity_actor_action(self):
        return concat_namespace(
            self.namespace, GraphKeyWords.Activity, GraphKeyWords.Actor, GraphKeyWords.Action, delimiter="_"
        )

    @property
    def activity_actor(self):
        return concat_namespace(self.namespace, GraphKeyWords.Activity, GraphKeyWords.Actor, delimiter="_")

    @property
    def activity_use_case_input(self):
        return concat_namespace(self.activity_use_case, GraphKeyWords.Input, delimiter="_")

    @property
    def activity_use_case_output(self):
        return concat_namespace(self.activity_use_case, GraphKeyWords.Output, delimiter="_")

    @property
    def activity_input_class(self):  # input class 候选池
        return concat_namespace(self.activity_input, GraphKeyWords.Class, delimiter="_")

    @property
    def activity_action_input_class(self):  # 异常登记
        return concat_namespace(
            self.namespace,
            GraphKeyWords.Activity,
            GraphKeyWords.Action,
            GraphKeyWords.Input,
            GraphKeyWords.Class,
            delimiter="_",
        )

    @property
    def activity_output_class(self):  # output class 候选池
        return concat_namespace(self.activity_output, GraphKeyWords.Class, delimiter="_")

    @property
    def activity_action_output_class(self):  # 异常登记
        return concat_namespace(
            self.namespace,
            GraphKeyWords.Activity,
            GraphKeyWords.Action,
            GraphKeyWords.Output,
            GraphKeyWords.Class,
            delimiter="_",
        )

    @property
    def activity_output_class_property(self):
        return concat_namespace(self.activity_output_class, GraphKeyWords.Property, delimiter="_")

    @property
    def activity_control_flow(self):
        return concat_namespace(self.namespace, GraphKeyWords.Activity, GraphKeyWords.ControlFlow, delimiter="_")

    @property
    def activity_control_flow_action(self):
        return concat_namespace(self.activity_control_flow, GraphKeyWords.Action, delimiter="_")

    @property
    def activity_swimlane(self):
        return concat_namespace(self.namespace, GraphKeyWords.Activity, GraphKeyWords.Swimlane, delimiter="_")

    @property
    def activity_swimlane_action(self):
        return concat_namespace(self.activity_swimlane, GraphKeyWords.Action, delimiter="_")

    @property
    def activity_swimlane_action_list(self):
        return concat_namespace(self.activity_swimlane_action, GraphKeyWords.List, delimiter="_")

    @property
    def activity_action_if_argument_class(self):  # if argument class候选池
        return concat_namespace(
            self.activity_action, GraphKeyWords.If, GraphKeyWords.Argument, GraphKeyWords.Class, delimiter="_"
        )

    @property
    def activity_control_flow_action_if(self):
        return concat_namespace(self.activity_control_flow_action, GraphKeyWords.If, delimiter="_")

    @property
    def activity_control_flow_action_if_argument(self):
        return concat_namespace(self.activity_control_flow_action_if, GraphKeyWords.Argument, delimiter="_")

    @property
    def activity_class_usage(self):
        return concat_namespace(
            self.namespace, GraphKeyWords.Activity, GraphKeyWords.Class, GraphKeyWords.Reference, delimiter="_"
        )

    @property
    def breakdown(self):
        return concat_namespace(self.namespace, GraphKeyWords.Breakdown, delimiter="_")

    @property
    def breakdown_use_case(self):
        return concat_namespace(self.breakdown, GraphKeyWords.UseCase, delimiter="_")

    @property
    def breakdown_use_case_reference(self):
        return concat_namespace(self.breakdown_use_case, GraphKeyWords.Reference, delimiter="_")

    @property
    def breakdown_use_case_reference_what(self):
        return concat_namespace(self.breakdown_use_case_reference, GraphKeyWords.Reference, delimiter="_")

    @property
    def breakdown_use_case_reference_todo(self):
        return concat_namespace(self.breakdown_use_case_reference, GraphKeyWords.ToDo, delimiter="_")

    @property
    def breakdown_use_case_reference_effect(self):
        return concat_namespace(self.breakdown_use_case_reference, GraphKeyWords.Effect, delimiter="_")
