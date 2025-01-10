"""
意图分类评估脚本

功能：
1. 读取Excel文件中的requirement，测试意图识别和任务分配
2. 评估分类性能：
   - 统计每个类别(TASK/QUICK/SEARCH/AMBIGUOUS)的样本数
   - 计算总体和各类别准确率
   - 生成混淆矩阵热力图
   - 输出详细分类报告(precision, recall, f1-score)
3. 保存评估结果

使用方法：
1. 输入：Excel文件，必须包含两列：
   - intention: 真实标签(0-3)
   - requirement: 需求
2. 输出：
   - 控制台打印统计信息和分类报告
   - confusion_matrix.png: 混淆矩阵热力图
   - intention-test-eval.xlsx: 带评估结果的Excel文件（retuirement, intention, intention_pred, assignee_pred, is_intention_accurate）
"""

import asyncio
from typing import Dict, List, Tuple
from unittest.mock import AsyncMock, patch

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.metrics import classification_report, confusion_matrix
from tqdm import tqdm

from metagpt.environment.mgx.mgx_env import MGXEnv
from metagpt.roles import Architect, ProductManager, ProjectManager
from metagpt.roles.di.data_analyst import DataAnalyst
from metagpt.roles.di.engineer2 import Engineer2
from metagpt.roles.di.team_leader import TeamLeader
from metagpt.schema import Message

REQUIREMENT = "requirement"
INTENTION_GROUND_TRUTH = "ground_truth_category"
ASSIGNEE_GROUND_TRUTH = "ground_truth_assignee"
INTENTION_PREDICT = "intention_pred"
ASSIGNEE_PREDICT = "assignee_pred"
INTENTION_ACCURATE = "is_intention_accurate"


class TeamLeaderForTesting(TeamLeader):
    """Testing class to capture intent_result from quick_think"""

    intent_result: str = ""
    command_rsp: str = ""
    commands: List[Dict] = []
    assignees: set = set()

    def publish_team_message(self, content: str, send_to: str):
        self._set_state(-1)

    # parse commands
    async def _act(self) -> Message:
        commands, ok, self.command_rsp = await self._parse_commands(self.command_rsp)
        if ok:
            self.commands = commands
        return await super()._act()

    # get intent result, mock SearchEnhancedQA.run
    async def _quick_think(self) -> Tuple[Message, str]:
        mock_search = AsyncMock(return_value="skip SearchEnhancedQA")
        # 使用 with patch 来 mock SearchEnhancedQA.run
        with patch("metagpt.actions.search_enhanced_qa.SearchEnhancedQA.run", mock_search):
            rsp_msg, intent_result = await super()._quick_think()
            self.intent_result = intent_result
            return rsp_msg, intent_result


async def run_mgx(requirement=""):
    team_leader = TeamLeaderForTesting()
    env = MGXEnv()
    env.add_roles(
        [
            team_leader,
            ProductManager(),
            Architect(),
            ProjectManager(),
            Engineer2(),
            DataAnalyst(),
        ]
    )

    env.publish_message(Message(content=requirement))
    await env.run()

    intent_category = ""
    if team_leader.intent_result and "Response Category:" in team_leader.intent_result:
        intent_category = team_leader.intent_result.split("Response Category:")[1].strip().split("\n")[0]
    # get assignees
    assignees = (
        set(cmd["args"]["assignee"] for cmd in team_leader.commands if cmd["command_name"] == "Plan.append_task")
        or None
    )

    return intent_category, assignees


async def process_batch(df_data: pd.DataFrame):
    category_list = []
    assignees_list = []

    for index, row in tqdm(df_data.iterrows(), total=len(df_data), desc="处理意图分类"):
        intent_category, assignees = await run_mgx(requirement=row[REQUIREMENT])
        print(f"intent_category: {intent_category}, assignees: {assignees}")
        category_list.append(intent_category)
        assignees_list.append(assignees)
    df_data[INTENTION_PREDICT] = category_list
    df_data[ASSIGNEE_PREDICT] = assignees_list

    return df_data


def eval_intention(df_data):
    # check if intention is correct
    # INTENTION_GROUND_TRUTH should be TASK/QUICK/SEARCH/AMBIGUOUS
    df_data[INTENTION_ACCURATE] = (df_data[INTENTION_GROUND_TRUTH] == df_data[INTENTION_PREDICT]).astype(int)

    # get all possible intention values
    actual_classes = sorted(set(df_data[INTENTION_GROUND_TRUTH].unique()) | set(df_data[INTENTION_PREDICT].unique()))

    # confusion matrix
    cm = confusion_matrix(df_data[INTENTION_GROUND_TRUTH], df_data[INTENTION_PREDICT], labels=actual_classes)

    # create heatmap
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=actual_classes, yticklabels=actual_classes)
    plt.title("Confusion Matrix")
    plt.xlabel("Predicted")
    plt.ylabel("True")
    plt.savefig("confusion_matrix.png")
    plt.close()

    # classification report
    report = classification_report(
        df_data[INTENTION_GROUND_TRUTH], df_data[INTENTION_PREDICT], target_names=actual_classes
    )
    print("\n分类报告:")
    print(report)


async def main(input_csv_file, output_csv_file):
    # read file
    df_data = pd.read_excel(input_csv_file)
    # get prediction
    df_data = await process_batch(df_data)

    # evaluation
    eval_intention(df_data)

    # save result
    df_data.to_excel(output_csv_file, index=False)


if __name__ == "__main__":
    input_csv_file = "/root/MetaGPT/intention_test.xlsx"
    output_csv_file = "/root/MetaGPT/intention_test_result.xlsx"

    asyncio.run(main(input_csv_file, output_csv_file))
