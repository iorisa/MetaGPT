#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest

from metagpt.actions.requirement_analysis.merge_swimlane import MergeDataFlow
from tests.metagpt.actions.requirement_analysis import prepare_graph_db


@pytest.mark.asyncio
async def test_merge_data_flow(context):
    await prepare_graph_db(context)

    action = MergeDataFlow(context=context)
    await action.run()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
