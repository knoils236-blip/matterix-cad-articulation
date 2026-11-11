---
name: matterix-cad-articulation
description: 引导用户一步步把 CAD 装配（SolidWorks 原生装配最佳，也可以是 STEP 等）重建成 Matterix 能直接加载的可动 USD 资产，带关节、行程、质量/惯量、碰撞，并生成 MatterixArticulationCfg 配置和双环境验收。每个阶段告诉用户需要提供哪些信息或数据（源文件、说明书、SolidWorks 配合导出、关节表、材料或重量），拿到后构建、把结果给用户确认，再进入下一阶段。关节可从 SolidWorks 配合自动推导（自带导出插件），没有 SolidWorks 或遇到铰链、转台等旋转机构时按用户给的关节表构建。当用户想让一台设备、工作站、龙门、滑台、夹爪、升降门等 CAD 模型“能动起来”“带物理属性”“做成 articulation”“给 Isaac Sim / Isaac Lab / Matterix 用”，问“做这个资产需要我准备什么”，或提到根据配合关系生成关节、从装配体提取材料质量时都应使用，即使没说 USD 或 skill 名字。只要静态碰撞体、器皿、自由刚体或修补已有 USD 资产时，用 matterix-asset-builder。
---

# CAD → Matterix 可动资产（引导式）

这个 skill 带着用户把一台 CAD 装配重建成带关节的 USD 资产。几何可以从文件里读出来，但“哪些东西会动、怎么动、多重”有一大半不在文件里，只在说明书和用户脑子里。所以流程按阶段推进：每个阶段先说清需要用户提供什么，拿到后动手，把结果摆给用户看，确认了再往下走。

流程在一台约 1000 个零件、1700 条配合的移液工作站上跑通过（47 个移动关节，双环境验收误差 ≤0.63 mm），STEP 加手写关节表的路线也实测过。只在这一台设备上验证过，换设备时遇到新情况要如实告诉用户。

## 怎么引导

- **一次只问当前阶段要的东西。** 开场就甩出十几个问题，用户答不上来，也不知道哪些要紧。每个阶段开头用一两句话说明这一步做什么、为什么需要他提供这些。
- **能自己查到的不要问。** 文件格式、外形尺寸、零件树、配合数量、缺材料的零件，都从文件和脚本输出里读。问用户的只有文件里没有的事实，以及需要他拍板的判断。
- **问得具体，带上你查到的证据。** 不问“拓扑对吗”，而是列出“托架-4 在 x=91 mm，和 X 动子 1 重合，是装在它上面吗”。能给选项就给选项（有 AskUserQuestion 工具时用它）。
- **用户答不上来时给出路。** 说明这一项缺了会怎样、可以先用什么占位、占位会写进限制。由用户决定是先去找资料还是带着占位继续，不要替他决定，也不要自己编一个值。
- **每个阶段结束给一个小结：** 做了什么、关键数字、下一步要什么。等用户确认后再进入下一阶段；用户说“你看着办，一路做完”时可以连着做，但需要他提供事实的地方仍然要停。
- **把答案记下来。** 在输出目录维护 `brief.md`，逐条记录用户给的信息、出处（说明书页码、型号手册、口述及日期）和还没解决的问题。这个流程常常跨会话（用户要去 Windows 上导出配合、去翻手册），新会话先读它，从没做完的阶段接着走；它也是最后 README 里“依据”和“限制”两节的来源。

阶段一览，用户问“需要我准备什么”时可以直接给他看：

| 阶段 | 需要用户提供 | 产出，给用户确认 |
|---|---|---|
| 1 需求 | CAD 文件、输出位置、要动的机构清单、说明书 | 需求记录和路线 |
| 2 几何 | 确认外形尺寸、隐藏件、透明件 | 静态 USD、预览图 |
| 3 关节 | 配合导出（SolidWorks），或关节表（轴、行程、归属） | 关节树 |
| 4 质量 | 缺材料零件的材料或重量 | 可动 USD、各 link 质量 |
| 5 验收 | 无，除非失败原因需要他判断 | 验收数值 |
| 6 交付 | 确认限制清单 | 资产、cfg、README |

## 阶段 1：需求和路线

先读目标 Matterix 仓库的 `AGENTS.md`。如果它要求以 MATTERIX 论文（Darvish 等，DOI 10.1038/s43588-025-00924-4）为依据，交付文档里要分开写三件事：论文 Methods “Asset generation” 里关节型资产来自关节描述（URDF/MJCF）；当前仓库已实现什么；本流程由 CAD 配合或用户关节表得到关节，属于新增扩展。

**向用户要：**
1. CAD 文件路径。看扩展名和文件是否存在；文件不存在就停下来说明，不要假装已经转换。
2. 输出目录。源 CAD 只读，所有产物写进输出目录。
3. 哪些机构需要动，用用户自己的话列出来（“龙门 XYZ、两个夹爪、前门”）。这份清单是后面验收关节树的标准：清单上有、树上没有的要补，树上多出来的要问。
4. 有没有说明书、型号手册、装配图。它们是轴向、行程、安装关系、外购件重量的依据，有就要路径。

**自己确认：** 运行环境是否就绪：带 Isaac Sim 的 Python（pip 版即可，例如 conda env `matterix`），`MATTERIX_PATH` 指向 Matterix checkout。同一时间只能跑一个 Matterix 进程（共用 `datasets/dataset.hdf5`，并发会报出误导性的错误），所以先看有没有正在跑的。

**定路线，并告诉用户接下来分别需要他做什么：**

| 情况 | 关节怎么来 | 用户之后要做的 |
|---|---|---|
| SolidWorks 装配，用户能在 Windows 上开 SolidWorks | 从配合推导（阶段 3A） | 装一次插件、导出一个 JSON；确认几处安装关系 |
| 只有 STEP 等中性格式，或用不了 SolidWorks | 按关节表构建（阶段 3B） | 给出每个机构的轴向、行程、运动件 |
| SolidWorks 装配里还有铰链、转台等旋转机构 | 3A 做直线轴，再按 3B 补旋转关节 | 两者都要 |

配合推导目前只出移动关节，所以旋转机构一律走 3B。把需求、路线和未决问题写进 `<out>/brief.md`。

## 阶段 2：几何

这一步不需要用户先提供什么，直接做：

```bash
python scripts/convert_cad.py <装配.SLDASM|.step> <out>/cad/raw.usdc          # HOOPS，约 40 s
python scripts/build_static.py <out>/cad/raw.usdc <out>/<Name>.usdc --root <Name> \
       [--unhide 被工作视图隐藏但实际存在的子装配名 ...] [--clear 透明件名子串 ... --clear-exclude 子串]
python scripts/render_preview.py <out>/<Name>.usdc <out> --front-axis +Y
```

`build_static.py` 把单位换成米、Z 朝上、原点放在可见外形的地面中心，可见网格全部设为静态三角网格碰撞体（摩擦 0.5、恢复系数 0），统计写入 `<out>.report.json`。

**给用户看并请他确认：**
- 外形尺寸（report 里的 `sizeMeters`）和实机或图纸对不对。差 1000 倍或 25.4 倍是单位问题。
- 预览图。问他有没有缺东西或多东西：CAD 工作视图里常把外壳、下机架整体隐藏，实机却存在，这类用 `--unhide` 显示出来；替代件、旧版本保持隐藏。report 里的 `hiddenMeshesWithoutCollider` 不为 0 时，把被隐藏的顶层子装配列给他选。
- 哪些件是透明的（亚克力罩、观察窗），用 `--clear`。

这一步的产物本身就是可用的静态资产（见 [references/troubleshooting.md](references/troubleshooting.md) 的“静态资产”一节）。如果用户其实只要静态的，到这里可以收尾。

## 阶段 3A：关节，从 SolidWorks 配合推导

**向用户要配合导出。** HOOPS 不导出配合（它们在 SLDASM 的私有压缩流里），所以需要用户在 Windows 的 SolidWorks 里跑一次插件。把这几步原样告诉他，并说明插件只读模型、不修改：
1. 把 `assets/solidworks_addin/` 拷到那台 Windows 机器，运行 `build.bat` 生成 `MatterixSwExporterSetup.exe`，以管理员身份安装（细节见其中的 `README_ZH.md`）；
2. 打开装配，点 **工具 → Matterix Isaac Sim Exporter → Export for Isaac Sim**，大装配要等几分钟；
3. 把生成的 `<装配>_isaacsim.json` 传回来，告诉你路径。

用户这段时间不在，把进度记进 `brief.md`。用户表示装不了或用不了时，改走 3B，不要卡在这里。

拿到 JSON 后先读 [references/sw-export.md](references/sw-export.md)（坐标约定和几个容易读错的字段），再推导：

```bash
python scripts/build_rig.py <export.json> <out>/rig_overrides.json <out>/rig.json   # 约 3 min；overrides 起初是 {}
python scripts/show_rig.py <out>/rig.json [--hide syringe_plunger] [--body 零件名子串]
```

`build_rig.py` 把配合线性化成刚体旋量约束求零空间，带行程的限位距离配合成为关节坐标，再按零件是否随动划分 link。算法和排错见 [references/kinematics.md](references/kinematics.md)。

第一遍几乎不会是 CLEAN，因为配合常常定不了“哪个托架装在哪个滑块上”，还会有把运动件停放在基准面上的配合。接下来是和用户的来回：

1. **对照阶段 1 的机构清单读树**：父子关系、轴、行程是否和说明书、常识一致（门竖直、龙门 X 挂在 Y 下面）。
2. **说明书写明的关系直接写进 overrides**，依据写页码或原句。
3. **说明书定不了的，列拓扑表问用户。** 用 `list_components.py <export.json>` 找坐标重合的安装关系，按“模块 → 你推断的承载件 → 坐标证据”列出来请他逐条确认或更正。用户同意后才写入，依据写“几何推断，用户某日确认”。
4. **重跑，直到 `show_rig.py` 打出 CLEAN。**

overrides 的写法见 `assets/overrides.example.json`：`weld`（固定关系）、`drop`（停放配合）、`names`（关节命名）、`stator_prefixes`（直线模组定子零件名的前缀，用来定父侧）。每条都带可复核的依据。依据不足时停下来问，不要为了收敛编一条。

**给用户看：** 最终的关节树，和机构清单逐项对上。清单上有而树上没有的，多半是旋转机构或 CAD 里没建限位配合，告诉他有两个办法：在 SolidWorks 里补限位配合后重新导出，或按 3B 给出轴和行程。

## 阶段 3B：关节，按用户给的关节表

没有配合，机构事实全部来自用户，所以这里问得最多。先读 [references/manual-rig.md](references/manual-rig.md)。

自己先做功课，让用户做选择题而不是填空题：

```bash
python scripts/list_components.py <out>/<Name>.usdc --depth 4 [--under 前缀] [--grep 叶子名子串 ...]
```

对阶段 1 清单里的每个机构，从零件树里找出候选的运动件，然后**逐个机构向用户确认**：
1. **运动件**：列出你认为随它一起动的子装配和零件，问有没有多了或少了的。
2. **类型和轴向**：平移还是旋转；方向用他能对上的说法（“沿设备长边”“向上”“绕左侧铰链边”），你再换算成坐标轴。旋转的要问转轴位置。
3. **行程**：从 CAD 保存位姿算起，两个方向各能走多少（mm 或度）。只知道总行程时，问保存位姿在行程的哪一头。
4. **装在谁上面**：固定在机架上，还是挂在另一个运动件上（Z 轴挂在 X 滑块上）。
5. **夹爪**：单指动还是双指对称动，各走多少。
6. **出处**：说明书、手册，还是他的经验值。照实记进 `brief.md`。

把答案写成 `rig.json`（格式在 manual-rig.md）。每个 link 的 `mass` 或 `density` 在阶段 4 问。

## 阶段 4：质量，构建可动 USD

```bash
python scripts/build_articulated.py --rig <out>/rig.json --static <out>/<Name>.usdc --out <out>/<Name>Articulated.usdc \
       [--export <export.json>] [--density "6061 铝合金=2700" ...]
```

3A 路线带 `--export`，质量、质心、惯量由 CAD 零件质量属性合成；3B 路线不带，用 rig.json 里每个 link 的 `mass` 或 `density`。

**3A：先构建一遍，看 `<out>.report.json` 的 `assumedWaterDensityParts`，再去问用户。** SolidWorks 对没设材料的零件按 1000 kg/m³ 算，只是占位；移液站上运动件 70 kg 里有 23 kg 是这样来的，大头是电爪、直线模组这类外购件。带着清单问，按估算质量从大到小，小件可以合并成一句：
- `namedMaterial` 已写明材料的，不用问，直接用 `--density "材料名=密度"` 重建；
- 外购件（电机、模组、电爪）：请用户给型号手册上的重量；
- 自制件：请用户说材料。

**3B：每个 link 向用户要重量或材料。** 外购件要手册重量；钣金、空心件要重量而不是材料，因为凸包把凹腔填实了，按密度算会偏重。

用户拿不到的，说明后果让他选：质量影响驱动力和接触表现，不影响关节到位精度；可以先用估值继续，这一项会连同总 kg 数写进 README 的限制。由他决定是否先去查。

然后从 `assets/articulated_cfg_template.py` 复制出 `<out>/<name>_articulated_cfg.py`，填好占位符。驱动刚度是统一的占位值，不是电机参数；用户关心力或速度上限时，问他要电机或模组的额定值再分轴改。

**给用户看：** 各 link 的质量表（report 的 `links`），请他扫一眼量级。

`build_articulated.py` 做的事，排错时用得上：运动零件移到所属 link 刚体下、位姿不变（3A 会断言 CAD 与 USD 坐标系只差一个平移）；运动零件碰撞用凸包，其余保持静态三角网格；资产内部不互相碰撞（link 之间靠 cfg 的 `enabled_self_collisions=False`，link 与静态几何之间在各 link 上用 FilteredPairs 过滤扫掠范围内的静态碰撞体）；每个关节带位置驱动；`base` 是带 ArticulationRootAPI 的锚点刚体，由 cfg 的 `fix_root_link=True` 固定到世界。

## 阶段 5：验收

全部实际运行并记录数值，不需要用户参与：

```bash
MATTERIX_PATH=... python scripts/validate_articulated.py --cfg <out>/<name>_articulated_cfg.py:<CLASS> --out <out>/articulated_validation.json
python scripts/render_preview.py <out>/<Name>Articulated.usdc <out> --front-axis +Y
```

| 检查 | 通过条件 | 证据 |
|---|---|---|
| 几何 | 外形尺寸经用户确认；隐藏件、透明件处理正确 | `<Name>.usdc.report.json`、预览图 |
| 坐标系（3A） | CAD → USD 只差一个平移，所有零件误差 <1e-6 m | `build_articulated` 的断言 |
| 运动学 | 关节树和用户的机构清单逐项对上；3A 还要 `show_rig` 输出 CLEAN、拓扑推断已经用户确认 | `rig.json`、`brief.md` |
| 质量 | 每个 link 质量大于 0、量级合理；估算的部分已处理或用户已同意列入限制 | `<out>.report.json` |
| Matterix 加载 | 两个环境都能生成；关节数和 rig 一致 | 验收 JSON |
| 驱动 | 两个环境分别把每个关节送到行程的 25% 和 75% 处，保持 4 s，误差全部 <1 mm（旋转关节 <1e-3 rad） | `maxJointErrorM`、`failingJoints` |
| 固定基座 | 根部漂移为 0 | `rootDriftM` |
| 外部碰撞 | 从顶部落下的烧杯停在资产上，没有穿透 | `probeRestZ` |

没通过时先跑 `--no-link-collisions` 对照：对照通过，是内部接触在挡运动；对照仍不通过，问题在运动学或驱动。排错表见 [references/troubleshooting.md](references/troubleshooting.md)。不要靠放宽 `--tol`、加大刚度或删关节来通过；要改的是根因：配合、拓扑、碰撞过滤、驱动力。

根因涉及机构事实时回去问用户，例如“气弹簧的杆端接在机架上还是门上”“这个方向和实机反了吗”。把结果告诉用户时给数值，失败项也照实说。

## 阶段 6：交付

输出目录里应该有：静态 USD 和可动 USD、cfg 文件、`rig.json`（3A 还有带依据的 `rig_overrides.json`）、构建报告和验收 JSON、`brief.md`、中文 README。

README 包含：用法示例、关节表（名称 / 父 link / 行程 / 轴 / 机构 / 依据）、构建命令、实测验证结果、论文依据、限制。限制一节如实写，**写完把这一节单独给用户过目**，这是他之后使用资产时最需要知道的部分。常见的有：
- 推断出的拓扑；用户口述、没有文档出处的关节；
- 配合推导只出移动关节，没补的旋转轴不会动；
- 对称夹爪只建了一个手指，或两指没有联动约束；
- 凸包会填实凹腔；
- 驱动参数不是电机实际参数；
- 估算质量的零件（清单和总 kg）；
- 共用导轨的两个滑块之间没有防撞约束；
- 只生成了 `MatterixArticulationCfg`，操作帧和语义行为需要在 Matterix 侧另配。

最后告诉用户怎么在他的环境里加载这个 cfg，问他还有没有要调整的。收尾时清理临时文件，`/tmp` 下的直接删，项目内的移入垃圾篓；保留报告、验收结果和 `brief.md`。
