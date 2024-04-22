#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from metagpt.repo_parser2 import RepoParser2


@pytest.mark.asyncio
async def test_repo_parser():
    repo_parser = RepoParser2(base_directory=Path(__file__).parent / "../data/code")

    symbols = await repo_parser.generate_symbols()
    assert symbols


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
