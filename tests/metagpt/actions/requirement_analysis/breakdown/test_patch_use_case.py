import pytest

from metagpt.actions.requirement_analysis.breakdown.patch_use_case import PatchUseCase
from tests.metagpt.actions.requirement_analysis.breakdown import prepare_graph_db


@pytest.mark.asyncio
async def test_patch(context):
    graph_db = await prepare_graph_db(context)
    action = PatchUseCase(graph_db=graph_db, context=context)
    await action.run()
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
