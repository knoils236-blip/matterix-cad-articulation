---
tags: [matterix-cad-articulation]
max_turns: 120
timeout_seconds: 3600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

移液站可动资产验收没过：/tmp/station_out/articulated_validation.json 里 door_1 和 gas_spring_1 各偏 5~6 mm，方向相反，其他关节都在 1 mm 以内。资产是用 matterix-cad-articulation 的脚本做的（overrides 在 /tmp/station_out/rig_overrides.json）。帮我查原因并修好，别靠放宽阈值。
