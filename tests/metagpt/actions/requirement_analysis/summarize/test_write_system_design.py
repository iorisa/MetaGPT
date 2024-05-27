import pytest

from metagpt.actions.requirement_analysis.summarize import WriteSystemDesign
from metagpt.const import METAGPT_ROOT, REQUIREMENT_FILENAME
from metagpt.utils.common import aread
from tests.metagpt.actions.requirement_analysis import prepare_graph_db


@pytest.mark.asyncio
async def test_write_design(context):
    await prepare_graph_db(context=context)
    activity_diagram = await aread(filename=METAGPT_ROOT / "tests/data/activity_diagram/1.md")
    await context.repo.resources.requirement_analysis.save(filename="activity.md", content=activity_diagram)
    requirement = await aread(filename=METAGPT_ROOT / "tests/data/requirement/6.txt")
    await context.repo.docs.save(filename=REQUIREMENT_FILENAME, content=requirement)

    action = WriteSystemDesign(context=context)
    await action.run()


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
