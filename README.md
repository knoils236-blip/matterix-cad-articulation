# matterix-cad-articulation

把 CAD 装配（SolidWorks 原生装配最佳，也可以是 STEP 等）转换成 Matterix / Isaac Sim 能直接加载的**可动 USD 资产**：带关节、行程、质量与惯量、碰撞，并生成 `MatterixArticulationCfg` 配置和双环境验收结果。

这是一个 Claude Code skill。它按阶段引导：每个阶段先说明需要用户提供什么，拿到后构建，把结果给用户确认，再进入下一阶段。

## 能力

- **关节从 SolidWorks 配合自动推导**，自带 SolidWorks 常驻导出插件（`assets/solidworks_addin/`），支持约 1000 零件、1700 条配合的装配。
- **没有 SolidWorks 时按关节表构建**：用户给出运动件、轴、行程、归属，脚本生成同样的关节树。
- **质量与惯量**：优先用 CAD 零件质量属性；缺材料的外购件按型号手册或用户输入修正。
- **碰撞**：运动件用凸包，静态件用三角网格；自动过滤 link 与扫掠范围内静态几何的接触。
- **验收**：在 Matterix 的两个环境里把每个关节驱动到行程的 25% 和 75%，检查到位误差、根部漂移和外部碰撞。

## 安装

作为个人 skill 使用：

```bash
git clone https://github.com/knoils236-blip/matterix-cad-articulation.git \
  ~/.claude/skills/matterix-cad-articulation
```

也可以放到某个项目的 `.claude/skills/matterix-cad-articulation/`，只在该项目里可用。

## 使用

在 Claude Code 里直接描述任务即可，例如：

- “把这个 SolidWorks 装配做成 Matterix 里能动的资产，龙门、夹爪、门都要能动”
- “根据装配体的配合关系帮我生成关节”
- “做这个资产需要我准备什么？”

也可以显式调用 `/matterix-cad-articulation`。

### 流程

| 阶段 | 需要用户提供 | 产出 |
|---|---|---|
| 1 需求 | CAD 文件、输出位置、要动的机构清单、说明书 | 需求记录和路线 |
| 2 几何 | 确认外形尺寸、隐藏件、透明件 | 静态 USD、预览图 |
| 3 关节 | 配合导出（SolidWorks），或关节表（轴、行程、归属） | 关节树 |
| 4 质量 | 缺材料零件的材料或重量 | 可动 USD、各 link 质量 |
| 5 验收 | 无，除非失败原因需要用户判断 | 验收数值 |
| 6 交付 | 确认限制清单 | 资产、cfg、README |

## 依赖

- **Isaac Sim 的 Python 环境**（pip 版即可），用于 CAD 转换、USD 构建和渲染；HOOPS CAD 转换器随 Isaac Sim 提供。
- **Matterix** checkout，验收时通过 `MATTERIX_PATH` 指定。
- **SolidWorks 2023 + Windows**（可选）：只有要从配合自动推导关节时才需要。插件在 Windows 上编译，只读模型。
- 同一时间只能运行一个 Matterix 进程（共用 `datasets/dataset.hdf5`）。

## 目录结构

```
SKILL.md                       skill 主流程和阶段说明
scripts/                       转换、构建、推导、验收脚本
references/                    关节推导、手工关节表、SolidWorks 导出、排错
assets/                        cfg 模板、overrides 示例、SolidWorks 导出插件
evals/                         4 个评测用例
```

## 验证状态与限制

- 流程在一台约 1000 个零件、1700 条配合的移液工作站上跑通过：47 个移动关节，双环境验收误差 ≤0.63 mm；STEP 加手写关节表的路线也实测过。**只在这一台设备上验证过**，换设备遇到新情况需要按实际情况处理。
- 从配合推导目前只生成移动关节；铰链、转台等旋转机构需要按关节表补充。
- SolidWorks 插件只在 SolidWorks 2023 上编译和导出过。
- 凸包碰撞会填实凹腔；估算质量的零件、推断出的拓扑、未联动的对称夹爪等，都会在最终交付的资产 README 的限制一节中如实列出。
- 驱动刚度是统一占位值，不是电机实际参数；需要力或速度上限时按轴替换。

## License

[MIT](LICENSE)
