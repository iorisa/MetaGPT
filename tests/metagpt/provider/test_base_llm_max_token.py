import json
import time

import pytest

from metagpt.configs.compress_msg_config import CompressType
from metagpt.configs.llm_config import LLMConfig
from metagpt.provider.base_llm import BaseLLM
from metagpt.provider.openai_api import OpenAILLM

TEST_MODELS_noGPT = ["claude-3-sonnet-20240229", "deepseek-coder"]
TEST_MODELS_MIX = ["anthropic/claude-3.5-sonnet", "gpt-4-32k-0613"]
BINARY_SEARCH_CONTENT_TEST_CASES = [
    {
        "content": "Hello, world! This is a test message.",
        "target_tokens": 3,
        "from_end": False,
        "description": "Short text truncated from start",
    },
    {
        "content": "Hello, world! This is a test message.",
        "target_tokens": 3,
        "from_end": True,
        "description": "Short text truncated from end",
    },
    {
        "content": "Hello, world! This is a test message.",
        "target_tokens": 13,
        "from_end": False,
        "description": "Short text truncated from start",
    },
    {
        "content": "Hello, world! This is a test message.",
        "target_tokens": 13,
        "from_end": True,
        "description": "Short text truncated from end",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 1,
        "from_end": False,
        "description": "Long text truncated from start",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 1,
        "from_end": True,
        "description": "Long text truncated from end",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 10,
        "from_end": False,
        "description": "Long text truncated from start",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 10,
        "from_end": True,
        "description": "Long text truncated from end",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 100,
        "from_end": False,
        "description": "Long text truncated from start",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 100,
        "from_end": True,
        "description": "Long text truncated from end",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 1000,
        "from_end": False,
        "description": "Long text truncated from start",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 1000,
        "from_end": True,
        "description": "Long text truncated from end",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 10000,
        "from_end": False,
        "description": "Long text truncated from start",
    },
    {
        "content": "Hello, world! " * 10000,
        "target_tokens": 10000,
        "from_end": True,
        "description": "Long text truncated from end",
    },
]
COMPRESS_MESSAGE_CONFIGS = [
    {"id": 1, "max_token": 128000, "range_count": 1000, "repeat_length": 100},
    {"id": 2, "max_token": 128000, "range_count": 100, "repeat_length": 1000},
    {"id": 3, "max_token": 128000, "range_count": 1000, "repeat_length": 2000},
    {"id": 4, "max_token": 500, "range_count": 5000, "repeat_length": 10},
]


class MockBaseLLM(BaseLLM):
    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()

    async def _achat_completion(self, messages: list[dict], timeout=3):
        pass

    async def acompletion(self, messages: list[dict], timeout=3):
        pass

    async def _achat_completion_stream(self, messages: list[dict], timeout: int = 3) -> str:
        pass


class MockOpenAILLM(OpenAILLM):
    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()


@pytest.mark.parametrize("test_case", BINARY_SEARCH_CONTENT_TEST_CASES)
def test_get_content_under_limit_token(test_case):
    """Test various scenarios for get_content_under_limit_token function"""
    start_time = time.time()
    base_llm = MockBaseLLM()
    base_llm.config.model = "gpt-4-32k"

    truncated = base_llm.get_content_under_limit_token(
        test_case["content"], target_token_count=test_case["target_tokens"], from_end=test_case["from_end"]
    )
    token_count = base_llm.count_tokens([{"role": "user", "content": truncated}])

    end_time = time.time()
    elapsed_time = end_time - start_time

    print(
        f"\n{test_case['description']} - original: '{test_case['content'][:50]}...' -> "
        f"truncated: '{truncated}' (tokens: {token_count})"
    )
    print(f"Time taken: {elapsed_time:.4f} seconds")

    assert isinstance(truncated, str)
    assert len(truncated) <= len(test_case["content"])
    # here should not be equal, because the target_token may be larger than original content's token count
    assert token_count <= test_case["target_tokens"]


@pytest.mark.parametrize("model", TEST_MODELS_noGPT)
def test_count_tokens_o_model(model):
    base_llm = MockBaseLLM()
    base_llm.config.model = model
    content = "Hello, world! This is a test message."
    token_count = base_llm.count_tokens([{"role": "user", "content": content}])
    print(f"token count: {token_count}")
    assert token_count == len(content) // 2


def test_count_tokens_GPT():
    openai_llm = MockOpenAILLM()
    model = "gpt-4o"
    openai_llm.config.model = model
    content = "Hello, world! This is a test message."
    import tiktoken

    encoding = tiktoken.encoding_for_model(model.replace("openai/", ""))
    expected_token_count = len(encoding.encode(content))

    token_count = openai_llm.count_tokens([{"role": "user", "content": content}])
    print(f"token count: {token_count}", "expected_token_count: ", expected_token_count)
    additional_token = 3 + 1 + 3
    assert token_count == expected_token_count + additional_token


@pytest.mark.parametrize("compress_type", list(CompressType))
@pytest.mark.parametrize("model", TEST_MODELS_MIX)
def test_compress_messages_no_effect(compress_type, model):
    base_llm = MockBaseLLM()
    base_llm.config.model = model
    messages = [
        {"role": "system", "content": "first system msg"},
        {"role": "system", "content": "second system msg"},
    ]
    for i in range(5):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    compressed = base_llm.compress_messages(messages, compress_type=compress_type)
    # should take no effect for short context
    assert compressed == messages


@pytest.mark.parametrize("compress_type", CompressType.cut_types())
@pytest.mark.parametrize("compress_config", COMPRESS_MESSAGE_CONFIGS)
def test_compress_messages_long(compress_type, compress_config):
    openai_llm = MockOpenAILLM()
    model = "gpt-4o"
    openai_llm.config.model = model
    max_token_limit = compress_config["max_token"]

    messages = [
        {"role": "system", "content": "first system msg"},
        {"role": "system", "content": "second system msg"},
    ]
    for i in range(compress_config["range_count"]):
        messages.append(
            {"role": "user", "content": f"u{i}" * compress_config["repeat_length"]}
        )  # ~2x10x0.5 = 10 tokens
        messages.append({"role": "assistant", "content": f"a{i}" * compress_config["repeat_length"]})

    start_time = time.time()
    compressed = openai_llm.compress_messages(messages, compress_type=compress_type, max_token=max_token_limit)
    end_time = time.time()
    original_token_count = openai_llm.count_tokens(messages)
    one_message_token_count = openai_llm.count_tokens(
        [{"role": "assistant", "content": f"a{i}" * compress_config["repeat_length"]}]
    )
    compressed_token_count = openai_llm.count_tokens(compressed)

    elapsed_time = end_time - start_time

    print(f"original_token_count: {original_token_count}")
    print(f"one_message_token_count: {one_message_token_count}")
    print(f"compressed_token_count: {compressed_token_count}")
    print(f"how many messages: {sum(1 for msg in compressed if isinstance(msg, dict))}")
    print(f"Time taken: {elapsed_time:.4f} seconds")
    assert 3 <= len(compressed) < len(messages)
    assert compressed[0]["role"] == "system" and compressed[1]["role"] == "system"
    assert compressed[2]["role"] != "system"


@pytest.mark.parametrize("compress_type", CompressType.cut_types())
def test_compress_messages_real(compress_type):
    openai_llm = MockOpenAILLM()
    model = "gpt-4o"
    openai_llm.config.model = model
    max_token_limit = 128000

    with open("./real_messages.json", "r") as f:
        messages = json.load(f)

    start_time = time.time()
    compressed = openai_llm.compress_messages(messages, compress_type=compress_type, max_token=max_token_limit)
    original_token_count = openai_llm.count_tokens(messages)

    compressed_token_count = openai_llm.count_tokens(compressed)
    end_time = time.time()
    elapsed_time = end_time - start_time

    print(f"original_token_count: {original_token_count}")
    print(f"compressed_token_count: {compressed_token_count}")
    print(f"how many messages: {sum(1 for msg in compressed if isinstance(msg, dict))}")
    print(f"Time taken: {elapsed_time:.4f} seconds")
    assert 3 <= len(compressed) <= len(messages)
    assert compressed[0]["role"] == "system"
    assert compressed[1]["role"] != "system"


@pytest.mark.parametrize("compress_type", CompressType.cut_types())
def test_compress_messages_long_no_sys_msg(compress_type):
    openai_llm = MockOpenAILLM()
    model = "gpt-4o"
    openai_llm.config.model = model
    max_token_limit = 128000

    messages = []
    for i in range(1000):
        messages.append({"role": "user", "content": "u1" * 100})  # ~2x10x0.5 = 10 tokens
        messages.append({"role": "assistant", "content": "a1" * 100})

    start_time = time.time()
    compressed = openai_llm.compress_messages(messages, compress_type=compress_type, max_token=max_token_limit)

    end_time = time.time()
    original_token_count = openai_llm.count_tokens(messages)
    compressed_token_count = openai_llm.count_tokens(compressed)
    end_time = time.time()
    elapsed_time = end_time - start_time

    print(f"original_token_count: {original_token_count}")
    print(f"compressed_token_count: {compressed_token_count}")
    print(f"Time taken: {elapsed_time:.4f} seconds")
    len_compressed_messages = sum(1 for msg in compressed if isinstance(msg, dict))
    print(f"how many messages: {len_compressed_messages}")
    assert compressed
    assert len_compressed_messages < 2000


def test_long_messages_no_compress():
    base_llm = MockBaseLLM()
    messages = [{"role": "user", "content": "1" * 10000}] * 10000
    compressed = base_llm.compress_messages(messages)
    assert len(compressed) == len(messages)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
