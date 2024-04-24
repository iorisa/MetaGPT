#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : __init__.py
@Desc    : The implementation of Chapter 2.2.1 of RFC225. https://deepwisdom.feishu.cn/wiki/VRq8wumeKiPcvIk9wcacwoIHnzc
"""
from metagpt.actions.requirement_analysis.breakdown.breakdown import BreakdownRequirementSpecifications
from metagpt.actions.requirement_analysis.breakdown.identify_use_case import IdentifyUseCase


__all__ = [BreakdownRequirementSpecifications, IdentifyUseCase]
