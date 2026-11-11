---
tags: [matterix-cad-articulation]
max_turns: 120
timeout_seconds: 3600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

我有一台移液工作站的 SolidWorks 装配 "/home/ry/projects/Matterix/USD/Pipetting station/Pipetting station装配/方案D-方案C-移液站3.SLDASM"，已经用插件导出了配合 "/home/ry/projects/Matterix/USD/Pipetting station/test/方案D-方案C-移液站3_isaacsim.json"。帮我做成 Matterix 里能动的资产，龙门、夹爪、门都要能动，带质量和碰撞。输出放到 /tmp/station_out/ 。我手上有说明书，上面写着 Y 轴直线电机控制龙门前后移动，X 轴直线电机带 Z 轴丝杆模组左右移动。
