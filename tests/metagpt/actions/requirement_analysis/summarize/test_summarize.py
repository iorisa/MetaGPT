import pytest

from metagpt.actions.requirement_analysis.summarize.summarize import Summarize
from tests.metagpt.actions.requirement_analysis import prepare_graph_db


@pytest.mark.asyncio
async def test_summarize(context):
    await prepare_graph_db(context)

    action = Summarize(context=context)
    await action.run()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
