#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from metagpt.actions.requirement_analysis.merge_swimlane import MergeDataFlow
from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.utils.common import aread


@pytest.mark.asyncio
async def test_merge_data_flow(context):
    context.kwargs.ns = Namespaces(namespace="RFC145")
    graph_db_filename = Path(__file__).parent / "../../../../data/graph_db/requirement_analyze.json"
    graph_db = await aread(filename=graph_db_filename, encoding="utf-8")
    await context.repo.docs.graph_repo.save(filename=context.repo.workdir.name + ".json", content=graph_db)

    action = MergeDataFlow(context=context)
    await action.run()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])