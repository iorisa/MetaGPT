#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest

from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.merge_swimlane import ActionMergeSwimlane
from metagpt.utils.common import concat_namespace, split_namespace
from tests.metagpt.actions.requirement_analysis import prepare_graph_db


@pytest.mark.asyncio
async def test_action_merge_swimlane(context):
    await prepare_graph_db(context)

    action = ActionMergeSwimlane(context=context)
    await action.run()

    activity_swimlane_namespace = concat_namespace(
        context.kwargs.namespace, GraphKeyWords.Activity, GraphKeyWords.Swimlane, delimiter="_"
    )
    rows = await action.graph_db.select(
        predicate=concat_namespace(activity_swimlane_namespace, GraphKeyWords.hasDetail)
    )
    assert rows
    use_case_namespace = concat_namespace(context.kwargs.namespace, GraphKeyWords.UseCase, delimiter="_")
    for i in rows:
        ns = split_namespace(i.subject)[0]
        assert ns == use_case_namespace


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
