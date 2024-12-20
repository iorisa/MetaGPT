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
   - intention-test-eval.xlsx: 带评估结果的Excel文件（retuirement, intention, intention_test, assignee_test, accurate）
"""
import asyncio
import os
import re
from typing import Tuple, List, Dict

import agentops

from metagpt.environment.mgx.mgx_env import MGXEnv
from metagpt.roles.di.team_leader import TeamLeader
from metagpt.schema import AIMessage, Message, UserMessage

import pandas as pd

from metagpt.roles.di.team_leader import TeamLeader
from sklearn.metrics import classification_report 
from metagpt.prompts.di.role_zero import (
    QUICK_RESPONSE_SYSTEM_PROMPT,
    QUICK_THINK_PROMPT,
    QUICK_THINK_TAG,
)
from metagpt.utils.report import ThoughtReporter

from metagpt.utils.common import  any_to_str
from metagpt.actions import UserRequirement
import copy
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.metrics import classification_report, confusion_matrix

input_csv_file = "/root/MetaGPT/intention-test.xlsx"
output_csv_file = "/root/MetaGPT/intention-test-result.xlsx"

class TeamLeaderForTesting(TeamLeader):
    """Testing class to capture intent_result from quick_think"""
    intent_result: str = ""
    command_rsp: str = ""
    commands: List[Dict] = []  

    # parse commands
    async def _act(self) -> Message:
        commands, ok, self.command_rsp = await self._parse_commands(self.command_rsp)
        if ok:
            self.commands = commands  
        return await super()._act()  
    
    
    # get intent result
    async def _quick_think(self) -> Tuple[Message, str]:
        """Override to capture intent_result and remove  SearchEnhancedQA"""
        answer = ""
        rsp_msg = None
        if self.rc.news[-1].cause_by != any_to_str(UserRequirement):
            # Agents themselves won't generate quick questions, use this rule to reduce extra llm calls
            return rsp_msg, ""

        # routing
        memory = self.get_memories(k=self.memory_k)
        context = self.llm.format_msg(memory + [UserMessage(content=QUICK_THINK_PROMPT)])
        async with ThoughtReporter() as reporter:
            await reporter.async_report({"type": "classify"})
            intent_result = await self.llm.aask(context, system_msgs=[self.format_quick_system_prompt()])
        self.intent_result = intent_result

        if "QUICK" in intent_result or "AMBIGUOUS" in intent_result:  # llm call with the original context
            cleaned_memory = []
            memory = self.get_memories(k=self.memory_k)

            for element in memory:
                # deep copy all element
                copied_element = copy.deepcopy(element)

                # If the answer contains the substring '[Message] from A to B:', remove it.
                pattern = r"\[Message\] from .+? to .+?:\s*"
                copied_element.content = re.sub(pattern, "", copied_element.content, count=1)
                cleaned_memory.append(copied_element)

            # cleaned_memory = self._clean_memory() # deep copy and
            async with ThoughtReporter(enable_llm_stream=True) as reporter:
                await reporter.async_report({"type": "quick"})
                answer = await self.llm.aask(
                    self.llm.format_msg(cleaned_memory),
                    system_msgs=[QUICK_RESPONSE_SYSTEM_PROMPT.format(role_info=self._get_prefix())],
                )
            # If the answer contains the substring '[Message] from A to B:', remove it.
            pattern = r"\[Message\] from .+? to .+?:\s*"
            answer = re.sub(pattern, "", answer, count=1)
            if "command_name" in answer:
                # an actual TASK intent misclassified as QUICK, correct it here, FIXME: a better way is to classify it correctly in the first place
                answer = ""
                intent_result = "TASK"
        elif "SEARCH" in intent_result:
            # 修改search部分，避免搜索工具报错程序停止
            return Message(content="Search intent detected, but search is skipped for testing"), intent_result

        if answer:
            self.rc.memory.add(AIMessage(content=answer, cause_by=QUICK_THINK_TAG))
            await self.reply_to_human(content=answer)
            rsp_msg = AIMessage(
                content=answer,
                sent_from=self.name,
                cause_by=QUICK_THINK_TAG,
            )

        return rsp_msg, intent_result
    


async def main(requirement="",  use_fixed_sop=False, allow_idle_time=30):
    
    team_leader = TeamLeaderForTesting()
    env = MGXEnv()
    env.add_roles(
        [
            team_leader
        ]
    )


    if requirement:
        env.publish_message(Message(content=requirement))
        await env.run()

        intent_category = ""
        if team_leader.intent_result and "Response Category:" in team_leader.intent_result:
            intent_category = team_leader.intent_result.split("Response Category:")[1].strip().split("\n")[0]
        # check commands
        print(f"-------------------------commands{team_leader.commands}")
        assignees = None
        if team_leader.commands:
            assignees = set()
            for cmd in team_leader.commands:
                if cmd["command_name"] == "Plan.append_task":
                    assignees.add(cmd["args"]["assignee"])

        return intent_category, assignees




def read_intention_test_file(file_path):
    df = pd.read_excel(file_path)
    return df


def eval_intention(df_data):
    # define intention map
    INTENTION_MAP = {
        "0": "TASK",
        "1": "QUICK", 
        "2": "SEARCH",
        "3": "AMBIGUOUS"
    }
    y_true = [] 
    y_pred = [] 
    class_counts = {
        "TASK": 0,
        "QUICK": 0,
        "SEARCH": 0,
        "AMBIGUOUS": 0
    }
    
    for index, row in df_data.iterrows():
        int_intent = int(row["intention"])
        ground_truth = INTENTION_MAP.get(str(int_intent), "UNKNOWN")
        test_result = row["intention_test"]

        class_counts[ground_truth] += 1
        
        y_true.append(ground_truth)
        y_pred.append(test_result)
        
        if ground_truth == test_result:
            df_data.at[index, "accurate"] = 1
        else:
            df_data.at[index, "accurate"] = 0


    print("\n各类别数量统计:")
    for class_name, count in class_counts.items():
        print(f"{class_name}: {count}条")
     
    actual_classes = sorted(set(y_true + y_pred))
    print("\n实际出现的类别:", actual_classes)
    
   
    # 计算混淆矩阵
    cm = confusion_matrix(y_true, y_pred, labels=actual_classes)
    
    # 创建热力图
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=actual_classes,
                yticklabels=actual_classes)
    plt.title('Confusion Matrix')
    plt.xlabel('Predicted')
    plt.ylabel('True')
    plt.savefig('confusion_matrix.png')
    plt.close()
    
    # classification report
    report = classification_report(y_true, y_pred, target_names=actual_classes)
    print("\n分类报告:")
    print(report)



if __name__ == "__main__":
    # NOTE: Add access_token to test github issue fixing
    os.environ["access_token"] = "ghp_xxx"
    # NOTE: Change the requirement to the one you want to test
    #       Set enable_human_input to True if you want to simulate sending messages in chatbox
    agentops.init(api_key="", auto_start_session=False, skip_auto_end_session=True)
    session = agentops.start_session()
    benchmark_test_file = input_csv_file
    df_data = read_intention_test_file(benchmark_test_file)

    # save intent_category to excel
    category_list = []
    assignees_list = []
    for index, row in df_data.iterrows():
        intent_category, assignees = asyncio.run(main(requirement=row["requirement"],  use_fixed_sop=False))
        print(f"intent_category: {intent_category}, assignees: {assignees}")
        category_list.append(intent_category)
        assignees_list.append(assignees)
    df_data['intention_test'] = category_list
    df_data['assignee_test'] = assignees_list
    

    # evaluation intention result
    eval_intention(df_data)
    accuracy = (df_data['accurate'] == 1).mean()
    print(f"\nAccuracy: {accuracy:.2%}")
    
    df_data.to_excel(output_csv_file, index=False)

    
    

