---
type: llm
focus: trace
weight: 1
---

The result matches this description: 助手说明 STEP 不含 SolidWorks 配合、配合推导不可用，但可以直接做：HOOPS 转几何/静态 USD，用 list_components.py 看零件树，按用户给的行程（滑台 300 mm、夹爪 20 mm）手写 rig.json 后用 build_articulated.py（不带 --export）构建并验收；向用户确认轴向、夹爪是单指还是双指各动多少，以及每个 link 的质量或材料依据，不自行编造；文件不存在时不假装已转换。
