import pytest

from metagpt.actions.requirement_analysis.analysis_report.write_report import (
    WriteReport,
)
from tests.metagpt.actions.requirement_analysis.breakdown import prepare_graph_db


async def test_write_report(context):
    graph_db = await prepare_graph_db(context)
    action = WriteReport(graph_db=graph_db, context=context)
    await action.run()
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
