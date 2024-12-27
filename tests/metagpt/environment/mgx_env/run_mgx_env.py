import asyncio
import os
import re
import threading
import time

import agentops

from metagpt.environment.mgx.mgx_env import MGXEnv
from metagpt.roles import Architect, Engineer, ProductManager, ProjectManager
from metagpt.roles.di.data_analyst import DataAnalyst
from metagpt.roles.di.frontend_engineer import FrontendEngineer
from metagpt.roles.di.team_leader import TeamLeader
from metagpt.schema import Message

# import agentops


async def main(requirement="", enable_human_input=False, use_fixed_sop=False, allow_idle_time=30):
    if use_fixed_sop:
        engineer = Engineer(n_borg=5, use_code_review=False)
    else:
        engineer = FrontendEngineer()

    env = MGXEnv()
    env.add_roles(
        [
            TeamLeader(),
            ProductManager(use_fixed_sop=use_fixed_sop),
            Architect(use_fixed_sop=use_fixed_sop),
            ProjectManager(use_fixed_sop=use_fixed_sop),
            engineer,
            DataAnalyst(),
        ]
    )

    if enable_human_input:
        # simulate human sending messages in chatbox
        stop_event = threading.Event()
        human_input_thread = send_human_input(env, stop_event)

    if requirement:
        if "@Alex" in requirement:
            user_defined_recipient = "Alex"
            env.publish_message(
                Message(content=requirement, send_to={user_defined_recipient}),
                user_defined_recipient=user_defined_recipient,
            )
        else:
            env.publish_message(Message(content=requirement))

    allow_idle_time = allow_idle_time if enable_human_input else 1
    start_time = time.time()
    while time.time() - start_time < allow_idle_time:
        if not env.is_idle:
            await env.run()
            start_time = time.time()  # reset start time

    if enable_human_input:
        print("No more human input, terminating, press ENTER for a full termination.")
        stop_event.set()
        human_input_thread.join()


def send_human_input(env, stop_event):
    """
    Simulate sending message in chatbox
    Note in local environment, the message is consumed only after current round of env.run is finished
    """

    def send_messages():
        while not stop_event.is_set():
            message = input("Enter a message any time: ")
            user_defined_recipient = re.search(r"@(\w+)", message)
            if user_defined_recipient:
                recipient_name = user_defined_recipient.group(1)
                print(f"{recipient_name} will receive the message")
                env.publish_message(
                    Message(content=message, send_to={recipient_name}), user_defined_recipient=recipient_name
                )
            else:
                env.publish_message(Message(content=message))

    # Start a thread for sending messages
    send_thread = threading.Thread(target=send_messages, args=())
    send_thread.start()
    return send_thread


GAME_REQ = "create a 2048 game"
GAME_REQ_ZH = "写一个贪吃蛇游戏"
WEB_GAME_REQ = "Write a 2048 game using JavaScript without using any frameworks, user can play with keyboard."
WEB_GAME_REQ_DEPLOY = "Write a 2048 game using JavaScript without using any frameworks, user can play with keyboard. When finished, deploy the game to public at port 8090."
TODO_APP_REQ = "Create a website widget for TODO list management. Users should be able to add, mark as complete, and delete tasks. Include features like prioritization, due dates, and categories. Make it visually appealing, responsive, and user-friendly. Use HTML, CSS, and JavaScript. Consider additional features like notifications or task export. Keep it simple and enjoyable for users.dont use vue or react.dont use third party library, use localstorage to save data."
FLAPPY_BIRD_REQ = "write a flappy bird game in pygame, code only"
SIMPLE_DATA_REQ = "load sklearn iris dataset and print a statistic summary"
WINE_REQ = "Run data analysis on sklearn Wine recognition dataset, and train a model to predict wine class (20% as validation), and show validation accuracy."
PAPER_LIST_REQ = """
Get data from `paperlist` table in https://papercopilot.com/statistics/iclr-statistics/iclr-2024-statistics/,
and save it to a csv file. paper title must include `multiagent` or `large language model`. *notice: print key variables*
"""
ECOMMERCE_REQ = """
Get products data from website https://scrapeme.live/shop/ and save it as a csv file.
**Notice: Firstly parse the web page encoding and the text HTML structure;
The first page product name, price, product URL, and image URL must be saved in the csv;**
"""
NEWS_36KR_REQ = """从36kr创投平台https://pitchhub.36kr.com/financing-flash 所有初创企业融资的信息, **注意: 这是一个中文网站**;
下面是一个大致流程, 你会根据每一步的运行结果对当前计划中的任务做出适当调整:
1. 爬取并本地保存html结构;
2. 直接打印第7个*`快讯`*关键词后2000个字符的html内容, 作为*快讯的html内容示例*;
3. 反思*快讯的html内容示例*中的规律, 设计正则匹配表达式来获取*`快讯`*的标题、链接、时间;
4. 筛选最近3天的初创企业融资*`快讯`*, 以list[dict]形式打印前5个。
5. 将全部结果存在本地csv中
**Notice: view the page element before writing scraping code**
"""
data_path = "data/titanic"
train_path = f"{data_path}/split_train.csv"
eval_path = f"{data_path}/split_eval.csv"
TITANIC_REQ = f"This is a titanic passenger survival dataset, your goal is to predict passenger survival outcome. The target column is Survived. Perform data analysis, data preprocessing, feature engineering, and modeling to predict the target. Report accuracy on the eval data. Train data path: '{train_path}', eval data path: '{eval_path}'."
CALIFORNIA_HOUSING_REQ = """
Analyze the 'Canifornia-housing-dataset' using https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_california_housing.html#sklearn.datasets.fetch_california_housing to predict the median house value. you need to perfrom data preprocessing, feature engineering and finally modeling to predict the target. Use machine learning techniques such as linear regression (including ridge regression and lasso regression), random forest, XGBoost. You also need to report the MSE on the test dataset
"""
STOCK_REQ = """Import NVIDIA Corporation (NVDA) stock price data from Yahoo Finance, focusing on historical closing prices from the past 5 years.
Summary statistics (mean, median, standard deviation, etc.) to understand the central tendency and dispersion of closingprices. Analyze the data for any noticeable trends, patterns, or anomalies over time, potentially using rolling averages or percentage changes.
Create a pot to visualize all the data analysis. Reserve 20% of the dataset for validaation. Train a predictive model on the training set. Report the modeel's validation accuracy, and visualize the result of prediction result.
"""
FIX_ISSUE1 = """
Write a fix for this issue: https://github.com/langchain-ai/langchain/issues/20453, 
you can fix it on this repo https://github.com/garylin2099/langchain,
checkout a branch named test-fix, commit your changes, push, and create a PR to the master branch of https://github.com/iorisa/langchain
"""
FIX_ISSUE2 = """
Write a fix for this issue https://github.com/geekan/MetaGPT/issues/1275.
You can fix it on the v0.8-release branch of this repo https://github.com/garylin2099/MetaGPT,
during fixing, checkout a branch named test-fix-1275, commit your changes, push, and create a PR to the v0.8-release branch of https://github.com/garylin2099/MetaGPT
"""
FIX_ISSUE3 = """
Write a fix for this issue https://github.com/geekan/MetaGPT/issues/1262.
You can fix it on this repo https://github.com/garylin2099/MetaGPT,
during fixing, checkout a branch named test-fix-1262, commit your changes, push, and create a PR to https://github.com/garylin2099/MetaGPT
"""
FIX_ISSUE_SIMPLE = """
Write a fix for this issue: https://github.com/mannaandpoem/simple_calculator/issues/1, 
you can fix it on this repo https://github.com/garylin2099/simple_calculator,
checkout a branch named test, commit your changes, push, and create a PR to the master branch of original repo.
"""
PUSH_PR_REQ = """
clone https://github.com/garylin2099/simple_calculator, checkout a new branch named test-branch, add an empty file test_file.py to the repo.
Commit your changes and push, finally, create a PR to the master branch of https://github.com/mannaandpoem/simple_calculator.
"""
IMAGE2CODE_REQ = "Please write a frontend web page similar to this image /Users/gary/Files/temp/workspace/temp_img.png, I want the same title and color. code only"
DOC_QA_REQ1 = "Tell me what this paper is about /Users/gary/Files/temp/workspace/2308.09687.pdf"
DOC_QA_REQ2 = "Summarize this doc /Users/gary/Files/temp/workspace/2401.14295.pdf"
DOC_QA_REQ3 = "请总结/Users/gary/Files/temp/workspace/2309.04658.pdf里的关键点"
DOC_QA_REQ4 = "这份报表/Users/gary/Files/temp/workspace/9929550.md中，营业收入TOP3产品各自的收入占比是多少"

TL_CHAT1 = """Summarize the paper for me"""  # expecting clarification
TL_CHAT2 = """Solve the issue at this link"""  # expecting clarification
TL_CHAT3 = """Who is the first man landing on Moon"""  # expecting answering directly
TL_CHAT4 = """Find all zeros in the indicated finite field of the given polynomial with coefficients in that field. x^5 + 3x^3 + x^2 + 2x in Z_5"""  # expecting answering directly
TL_CHAT5 = """Find the degree for the given field extension Q(sqrt(2), sqrt(3), sqrt(18)) over Q."""  # expecting answering directly
TL_CHAT6 = """True or False? Statement 1 | A ring homomorphism is one to one if and only if the kernel is {{0}},. Statement 2 | Q is an ideal in R"""  # expecting answering directly
TL_CHAT7 = """Jean has 30 lollipops. Jean eats 2 of the lollipops. With the remaining lollipops, Jean wants to package 2 lollipops in one bag. How many bags can Jean fill?"""  # expecting answering directly
TL_CHAT9 = """What's your name?"""
TL_CHAT10 = "Hi"
TL_CHAT11 = "Tell me about your team"
TL_CHAT12 = "What can you do"
CODING_REQ1 = "写一个java的hello world程序"
CODING_REQ2 = "python里的装饰器是什么"
CODING_REQ3 = "python里的装饰器是怎么用的，给我个例子"

EXAMPLE = """
# /root/code/TemplateRecommendation/MetaGPT/data/护肤品.csv 基于护肤品数据集,需要开发一个产品浏览网站。整体页面采用左侧菜单栏和右侧内容区的布局方式。目前左侧菜单栏只需要添加"数据概览"这一个选项。
在数据概览页面中,用户可以通过"类型"、"品牌"和"皮肤类型"进行产品筛选。其中"皮肤类型"支持多选,包括“干油混合皮肤“、“干性皮肤”、“正常皮肤”、“油性皮肤”、“敏感肌”这五种类型。筛选后的数据需要以表格形式展示出来,表格中应包含产品名、价格、评分以及适用皮肤类型。其中价格和评分支持点击表头进行升序、降序以及默认排序，需要比较醒目。对于产品适合的皮肤类型,采用"✅"符号来标识 - 适合该皮肤类型则显示"✅"，不适合则显示空白。表格默认每页展示10条数据，支持分页浏览。产品名称支持点击交互,点击后弹窗显示该产品的详细成分信息。
注意
1. 网站的名称叫做：护肤品大全
2. 网站的风格使用清新风格，但是得保障数据清晰可见
3. David需要一同给一份数据说明给到Alex
"""

EXAMPLE = """
@Alex
我有一个月的工作时间记录CSV，包含任务、时长、类型、完成状态等信息。请基于这些数据制作一个工作时间分配看板，展示各类任务的时间投入情况。\n请基于以下要求设计并实现看板:\n1. 展示日常时间分布图。\n2. 提供任务类型占比统计。\n3. 显示完成度统计表。\n4. 展示每日专注度图。\n5. 提供工作时段热图。\n6. 提供报表导出功能\n\n下面是我的输入材料:
/root/code/TemplateRecommendation/MetaGPT/data/工作时间记录.csv
"""

#
# EXAMPLE = """
# @Alex Help me design a personal business card webpage. My YouTube channel name is 'Garystech'.
# """

# EXAMPLE = """
# ``` "/api/v1/admin/users": { "get": { "tags": [ "管理员模块" ], "summary": "获取用户列表", "operationId": "list_user_api_v1_admin_users_get", "parameters": [ { "name": "cur_page", "in": "query", "required": false, "schema": { "type": "integer", "exclusiveMinimum": 0, "default": 1, "title": "Cur Page" } }, { "name": "page_num", "in": "query", "required": false, "schema": { "type": "integer", "exclusiveMinimum": 0, "default": 20, "title": "Page Num" } }, { "name": "status", "in": "query", "required": false, "schema": { "anyOf": [ { "$ref": "#/components/schemas/UserStatus" }, { "type": "null" } ], "title": "Status" } } ], "responses": { "200": { "description": "Successful Response", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/UserListOut" } } } }, "422": { "description": "Validation Error", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/HTTPValidationError" } } } } } }, "patch": { "tags": [ "管理员模块" ], "summary": "修改用户信息", "operationId": "update_user_api_v1_admin_users_patch", "requestBody": { "required": true, "content": { "application/json": { "schema": { "$ref": "#/components/schemas/UserUpdateIn" } } } }, "responses": { "200": { "description": "Successful Response", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/UserUpdateOut" } } } }, "422": { "description": "Validation Error", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/HTTPValidationError" } } } } } } }, "UserStatus": { "type": "string", "enum": [ "active", "pending", "activating" ], "title": "UserStatus" }, ``` @Alex 实现一个管理员页面，用于通过用户申请请求，需要两个功能，查看用户列表支持pending或者active筛选用户 只有pending的用户需要激活 支持id或者email激活 API_BASE_URL和鉴权token 允许设置
#
# """

# EXAMPLE = """
# @Alex  Using react template develop a pretty personal card for me. My name is Alex, a traveller and vlogger, my tiktok and youtube account are both named alex_travel. On the page, put a main video block with this link (https://youtu.be/GZbU3zvTTG8?si=gCxmCdNyZ-Vdm9_Z) in the middle, which is my vlogger to Europe. Then search three images for Great Wall, Pyramids, and African animals and place them in a row under the video. Use a scenic snow view of the Mount Alps as the background.
#
# """


if __name__ == "__main__":
    # NOTE: Add access_token to test github issue fixing
    os.environ["access_token"] = "ghp_xxx"
    # NOTE: Change the requirement to the one you want to test
    #       Set enable_human_input to True if you want to simulate sending messages in chatbox
    agentops.init(api_key="", auto_start_session=False, skip_auto_end_session=True)
    session = agentops.start_session()
    asyncio.run(main(requirement=EXAMPLE, enable_human_input=False, use_fixed_sop=False))
