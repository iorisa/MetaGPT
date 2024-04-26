#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest

from metagpt.actions.requirement_analysis.activity import OrderActions
from tests.metagpt.actions.requirement_analysis import prepare_graph_db


@pytest.mark.asyncio
async def test_order_action(context):
    await prepare_graph_db()

    action = OrderActions(context=context)
    await action.run()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
