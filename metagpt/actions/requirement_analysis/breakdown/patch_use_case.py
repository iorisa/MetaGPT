#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : patch_use_case.py
@Desc    : The implementation of the Chapter 2.2.3 of RFC225.
"""
from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.actions.requirement_analysis.breakdown_common import (
    BreakdownReferenceType,
    BreakdownUseCaseDetail,
    EffectPatch,
    Issue5W1H,
    IssueWhatPatch,
    Section,
    Sections,
    ToDoPatch,
)
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.logs import logger
from metagpt.schema import Message
from metagpt.utils.common import (
    add_affix,
    concat_namespace,
    general_after_log,
    parse_json_code_block,
    remove_affix,
    split_namespace,
)


class PatchUseCase(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()
        rows = await self.graph_db.select(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown, GraphKeyWords.OriginalRequirement + GraphKeyWords.List
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown, GraphKeyWords.Is_),
        )
        sections = Sections.model_validate_json(remove_affix(split_namespace(rows[0].object_)[-1]))
        rows = await self.graph_db.select(
            predicate=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference, GraphKeyWords.Has_ + GraphKeyWords.Reference
            )
        )
        for i in rows:
            use_case_detail = BreakdownUseCaseDetail.model_validate_json(remove_affix(split_namespace(i.subject)[-1]))
            type_ = BreakdownReferenceType.model_validate_json(remove_affix(split_namespace(i.object_)[-1]))
            await self._patch(use_case_detail, type_, sections)

        await self.graph_db.save()
        return Message(content="", cause_by=self)

    async def _patch(self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, sections: Sections):
        section = None
        for i in sections.sections:
            if set(i.tags) == set(use_case_detail.tags):
                section = i
                break
        if type_.is_issue:
            await self._patch_issue(use_case_detail, type_, section)
        if type_.is_todo:
            await self._patch_todo(use_case_detail, type_, section)
        if type_.is_effect:
            await self._patch_effect(use_case_detail, type_, section)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _patch_issue(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        original_text = section.content
        issue = type_.reference
        prompt = f"## Original Text\n{original_text}\n## Use Case\n{use_case_detail.use_case}\n## Issue\n{issue}\n"
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                '- "Use Case" is meant to address the problems raised in the "Issue";',
                '- "Original Text" provides the complete context information;',
                '- According to the "5W1H" method, Breaking down the "Issue" by quoting the original text from "Original Text". ',
                "Return a markdown JSON object with:\n"
                '- a "who" key containing the use case actors. Leave it blank if it\'s not mentioned.\n'
                '- a "why_who" key explaining why "who" is filled like this.\n'
                '- a "what" key containing what the issue is in detail. Leave it blank if it\'s not mentioned.\n'
                '- a "why_what" key explaining why "what" is filled like this.\n'
                '- a "when" key containing when the scenario of the issue occurs. Leave it blank if it\'s not mentioned.\n'
                '- a "why_when" key explaining why "when" is filled like this.\n'
                '- a "why" key explaining why these scenario is considered as an issue. Leave it blank if it\'s not mentioned.\n'
                '- a "why_why" key explaining why "why" is filled like this.\n'
                '- a "how" key containing who to do. Leave it blank if it\'s not mentioned.\n'
                '- a "why_how" key explaining why "how" is filled like this.',
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        what = Issue5W1H.model_validate_json(json_blocks[0])
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case_reference_what, GraphKeyWords.Is_),
            object_=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(what.model_dump_json())
            ),
        )

        await self._patch_issue_what(
            original_text=original_text, use_case_detail=use_case_detail, issue=issue, what=what
        )

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _patch_issue_what(
        self, original_text: str, use_case_detail: BreakdownUseCaseDetail, issue: str, what: Issue5W1H
    ):
        prompt = (
            f"## Original Text\n{original_text}\n"
            f"## Use Case\n{use_case_detail.use_case}\n"
            f"## Issue\n{issue}\n"
            f"### What\n{what.what}\n"
            f"### Why\n{what.why}\n"
        )
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                '"Use Case" is meant to address the problems raised in the "Issue";',
                '"Original Text" provides the complete context information;',
                '"Issue" has been broken down with "5W1H" method.',
                'Is the description in "What" able to establish clear objectives and indicators?',
                'Is the description in "What" actionable and checkable? If so:\n'
                "- How can the data for checks be obtained? Provide sufficiently specific guidance.\n"
                "- Which measurement tools and methods should be used? Provide sufficiently specific guidance.\n"
                "- Which indicators should be selected? Provide sufficiently specific guidance.\n"
                "- How to avoid subjective issues in measurement results? Provide sufficiently specific guidance.\n"
                "- What are the criteria for solving the issue? What are the quality requirements when solving the issue? Provide sufficiently specific guidance.",
                "Return a markdown JSON object with:\n"
                '- a "is_clear" key containing a boolean key about whether the description in "What" able to establish clear objectives and indicators;\n'
                '- a "is_actionable" key containing a boolean key about whether the description in "What" actionable and checkable;\n'
                '- a "data_for_checks" key containing a string list type of object about how the data for checks can be obtained with sufficiently specific guidance if "is_actionable" is filled with true;\n'
                '- a "measurement_tools_and_methods" key containing a string  list type object about which measurement tools and methods are used with sufficiently specific guidance if "is_actionable" is filled with true;\n'
                '- a "indicators" key containing a string list type object about which indicators are selected with sufficiently specific guidance   if "is_actionable" is filled with true;\n'
                '- a "avoiding_subjective_issues" key containing a string list type object about how to avoid subjective issues in measurement results  with sufficiently specific guidance   if "is_actionable" is filled with true;\n',
                '- a "criteria" key containing a string list type object about what the criteria are for solving the issue;\n'
                '- a "quality_requirements" key containing a string list type object about what the quality requirements are when solving the issue;',
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        patch = IssueWhatPatch.model_validate_json(json_blocks[0])
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, GraphKeyWords.Has_ + GraphKeyWords.Detail
            ),
            object_=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_what, add_affix(patch.model_dump_json())
            ),
        )

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _patch_todo(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        original_text = section.content
        todo = type_.todo
        prompt = f"## Original Text\n{original_text}\n## Use Case\n{use_case_detail.use_case}\n## TODO\n{todo}\n"
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                '- "Use Case" aims to implement the "how to do" outlined in the "TODO";',
                '- "Original Text" provides the complete context information;',
                '- What are the task objectives of the "Use Case"? What are the expected outcomes? What are the criteria for completing the task? What are the quality requirements when completing the task? Provide sufficiently specific guidance.',
                '- What information, data, or resources inputs are needed to accomplish the tasks in the "Use Case," and where do they come from? These inputs include those needed for development, operation, as well as the inputs required by the functionality itself. Provide sufficiently specific guidance, including specific items or information to be provided.',
                '- What external environmental factors are needed to complete the tasks in the "Use Case," and what are the potential constraints that may affect task implementation? Provide sufficiently specific guidance.',
                '- What are the potential risks that may hinder the completion of tasks in the "Use Case"? How should each risk be addressed? Provide sufficiently specific guidance.',
                '- What are the expected outputs of the "Use Case"? Provide sufficiently specific guidance, including specific items or information to be delivered.',
                "Return a markdown JSON object with:\n"
                '- a "objectives" key containing a string list type object about what the task objectives of the "Use Case" are;\n'
                '- a "expected_outcomes" key containing a string list type object about what the expected outcomes are;\n'
                '- a "criteria" key containing a string list type object about what the criteria are for completing the task;\n'
                '- a "quality_requirements" key containing a string list type object about what the quality requirements are when completing the task;\n'
                '- a "inputs_needs" key containing a string list type object about what information, data, or resources inputs are needed to accomplish the tasks in the "Use Case";\n'
                '- a "external_environmental_factors" containing a string list type object about what external environmental factors are needed to complete the tasks in the "Use Case";\n'
                '- a "potential_risks" key containing a string list type object about what the potential constraints are that may affect task implementation;\n'
                '- a "risk_prevention" key containing a string list object about how to address these potential risks.\n'
                '- a "expected_outputs" key containing a string list type object about what the expected outputs of the "Use Case" are;',
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        todo = ToDoPatch.model_validate_json(json_blocks[0])
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_todo, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case_reference_todo, GraphKeyWords.Is_),
            object_=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_todo, add_affix(todo.model_dump_json())
            ),
        )

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(6),
        after=general_after_log(logger),
    )
    async def _patch_effect(
        self, use_case_detail: BreakdownUseCaseDetail, type_: BreakdownReferenceType, section: Section
    ):
        original_text = section.content
        effect = type_.effect
        prompt = f"## Original Text\n{original_text}\n## Use Case\n{use_case_detail.use_case}\n## Effect\n{effect}\n"
        rsp = await self.llm.aask(
            prompt,
            system_msgs=[
                '- "Use Case" aims to achieve the effects described in the "Effect";',
                '- "Original Text" provides the complete context information;',
                '- What are the specific objectives and expected outputs to be achieved by "Effect", and why is it important to achieve this outcome? Provide sufficiently specific guidance.',
                '- What are the criteria for achieving "Effect"? What are the quality requirements when achieving "Effect"? Provide sufficiently specific guidance.',
                '- Are the objectives of "Effect" measurable, and by what means can the achievement of these objectives be evaluated?  Provide sufficiently specific guidance.',
                '- What data, information, or resources are required as inputs to achieve "Effect"? Provide sufficiently specific guidance.',
                '- What steps, methods, and technologies are necessary to achieve "Effect"?  Provide sufficiently specific guidance.',
                '- What external environmental factors are needed to complete the tasks in the "Use Case," and what are the potential constraints that may affect task implementation? Provide sufficiently specific guidance.',
                '- What challenges and risks might be encountered in achieving "Effect", and how should they be addressed?  Provide sufficiently specific guidance.',
                "Return a markdown JSON object with:\n"
                '- an "objectives" key containing a string list object about what the specific objectives are;\n'
                '- an "expected_outputs" key containing a string list object about what the expected outputs to be achieved by "Effect" are;\n'
                '- a "criteria" key containing a string list type object about what the criteria are for achieving "Effect";\n'
                '- a "quality_requirements" key containing a string list type object about what the quality requirements are when achieving "Effect";\n'
                '- an "is_measurable" key containing a boolean value about whether the objectives of "Effect"  are measurable;\n'
                '- an "evaluations" key containing a string list object about what means can the achievement of these objectives be evaluated;\n'
                '- an "inputs_needs" key containing a string list object about what data, information, or resources are required as inputs to achieve "Effect";\n'
                '- a "steps" key containing a string list object about what steps are necessary to achieve "Effect";\n'
                '- a "methods" key containing a string list object about what methods are necessary to achieve "Effect";\n'
                '- a "technologies" key containing a string list object about what technologies are necessary to achieve "Effect";\n'
                '- a "external_environmental_factors" containing a string list type object about what external environmental factors are needed to achieve "Effect";\n'
                '- a "potential_risks" key containing a string list object about what challenges and risks might be encountered in achieving "Effect";\n'
                '- a "risk_prevention" key containing a string list object about how to address these potential risks.',
            ],
        )
        logger.info(rsp)
        json_blocks = parse_json_code_block(rsp)
        effect = EffectPatch.model_validate_json(json_blocks[0])
        await self.graph_db.insert(
            subject=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_effect, add_affix(use_case_detail.model_dump_json())
            ),
            predicate=concat_namespace(self.context.kwargs.ns.breakdown_use_case_reference_effect, GraphKeyWords.Is_),
            object_=concat_namespace(
                self.context.kwargs.ns.breakdown_use_case_reference_effect, add_affix(effect.model_dump_json())
            ),
        )
