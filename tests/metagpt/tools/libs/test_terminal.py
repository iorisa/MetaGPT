import pytest

from metagpt.const import DATA_PATH, METAGPT_ROOT
from metagpt.tools.libs.terminal import Terminal


@pytest.mark.asyncio
async def test_terminal():
    terminal = Terminal()

    await terminal.run_command(f"cd {METAGPT_ROOT}")
    output = await terminal.run_command("pwd")
    assert output.strip() == str(METAGPT_ROOT)

    # pwd now should be METAGPT_ROOT, cd data should land in DATA_PATH
    await terminal.run_command("cd data")
    output = await terminal.run_command("pwd")
    assert output.strip() == str(DATA_PATH)

    assert terminal.cwd == str(DATA_PATH)


@pytest.mark.asyncio
async def test_terminal_switch_tab():
    terminal = Terminal(timeout=5)
    output = await terminal.run_command("echo abc && sleep 60")
    print(output)
    assert "abc" in output
    assert len(terminal.tabs) == 2


@pytest.mark.skip
@pytest.mark.asyncio
async def test_terminal_typing():
    terminal = Terminal(timeout=5)
    command = 'python -c "x = input(); print(int(x) * 2)"'
    output1 = await terminal.run_command(command)
    print(output1)
    await terminal.switch_tab("00")
    output2 = await terminal.run_command("2")
    print(output2)
    assert "4" in output2


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
