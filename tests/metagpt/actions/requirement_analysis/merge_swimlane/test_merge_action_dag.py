#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.merge_swimlane.merge_action_dag import (
    MergeActionDAG,
)
from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.utils.common import aread, concat_namespace


@pytest.mark.asyncio
async def test_merge_action_dag(context):
    context.kwargs.ns = Namespaces(namespace="RFC145")
    graph_db_filename = Path(__file__).parent / "../../../../data/graph_db/requirement_analyze.json"
    graph_db = await aread(filename=graph_db_filename, encoding="utf-8")
    await context.repo.docs.graph_repo.save(filename=context.repo.workdir.name + ".json", content=graph_db)

    action = MergeActionDAG(context=context)
    await action.run()

    activity_swimlane_namespace = concat_namespace(
        context.kwargs.namespace, GraphKeyWords.Activity, GraphKeyWords.Swimlane, delimiter="_"
    )
    rows = await action.graph_db.select(predicate=concat_namespace(activity_swimlane_namespace, GraphKeyWords.hasPreOp))
    assert rows


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
