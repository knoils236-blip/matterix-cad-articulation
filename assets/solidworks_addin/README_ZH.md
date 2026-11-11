# Matterix Isaac Sim Exporter（SolidWorks 常驻插件）

这是 SolidWorks 2023 的 COM 插件，SolidWorks 启动时会自动加载。打开装配体后点 **工具 → Matterix Isaac Sim Exporter → Export for Isaac Sim**，就会把装配结构、配合、零件材料和质量属性导出成 JSON，供这边构建 Isaac Sim / Matterix 的 USD（关节、刚体分组、质量与惯量）使用。插件只读取数据，不会修改模型。

## 一次性构建（在装有 SolidWorks 的 Windows 上）

1. 把整个 `solidworks_addin` 文件夹复制到 Windows。
2. 双击 `build.bat`，生成 `dist\MatterixSwExporterSetup.exe`。
   - 编译用的是 Windows 自带的 .NET Framework 4 编译器，引用的是 SolidWorks 安装目录里的互操作 DLL（`C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist`），不需要额外安装任何东西。
   - 如果 SolidWorks 不在默认目录，在命令行把 redist 目录作为参数传进去：`build.bat "D:\...\SOLIDWORKS\api\redist"`。
   - 互操作类型会嵌入到插件 DLL 里，安装后运行不依赖这些 DLL。

为什么不能在 Linux 这边直接编好 exe：编译时必须引用达索的 SolidWorks 互操作 DLL，这些 DLL 只在装了 SolidWorks 的机器上才有。NuGet 上有第三方转发的版本，但来源和授权都不清楚，所以不用。

## 安装 / 卸载

- 先**关闭 SolidWorks**，再双击 `MatterixSwExporterSetup.exe`，按提示授予管理员权限。安装程序会做三件事：
  1. 把插件复制到 `C:\Program Files\Matterix\SwExporter\`；
  2. 用系统自带的 RegAsm 注册 COM；
  3. 写入 SolidWorks 插件注册表项，并设为启动时加载。
- 重新打开 SolidWorks，"工具"菜单里会出现 **Matterix Isaac Sim Exporter**。如果没有，到 工具 → 插件 里勾选它。
- 卸载：关闭 SolidWorks，在命令行运行 `MatterixSwExporterSetup.exe /uninstall`。
- 更新：重新构建后再运行一次安装程序，会覆盖旧版本。

`MatterixSwExporterSetup.exe` 是单个文件，可以拿到其他装有 SolidWorks 的 Windows 电脑上直接安装。

## 使用

1. 打开顶层装配 `方案D-方案C-移液站3.SLDASM`，激活需要的配置。
2. 点 工具 → Matterix Isaac Sim Exporter → Export for Isaac Sim。这个菜单只在当前文档是装配体时才能点。
3. 插件会先把轻化零部件全部还原（大装配要等几分钟），然后在装配体同目录写出 `方案D-方案C-移液站3_isaacsim.json`，并弹窗显示导出数量。
4. 把这个 JSON 交给构建流程（`scripts/build_rig.py`、`build_articulated.py` 的输入）。

出错时会弹窗显示完整的异常信息，插件不会让 SolidWorks 崩溃。把弹窗内容发给我就行。

## 导出内容（`matterix-sw-export-v1`，单位全部为 SI）

| 字段 | 内容 | USD 构建中的用途 |
|---|---|---|
| `components` | 实例完整名（如 `子装配-1/零件-1`）、父级、文件、引用配置、是否压缩/固定/可见、子装配是否柔性、`Transform2.ArrayData`（3×3 旋转、平移 m、缩放） | 对上 HOOPS 转换出的几何，确定零件的世界位姿 |
| `mates` | 顶层和各子装配实例中的全部配合，包括配合文件夹里的：所属装配、特征名与类型、`swMateType_e` 码和名称、对齐、翻转、尺寸（距离/角度/限制的数值与上下限、齿轮比）；每个配合实体的零件、参考类型和 `EntityParams`（点、方向、半径） | 合并刚体，推导剩余自由度、关节类型、轴、锚点和行程 |
| `parts` | 每个（零件文件, 引用配置）的材料名/材料库、密度、质量、体积、表面积、质心、质心处惯性张量、文件级与配置级自定义属性（型号、厂家等） | 刚体质量和惯量；HOOPS 默认按 1000 kg/m³ 算，这里用真实材料修正 |

质量属性按零件文件的**当前激活配置**计算（记录在 `massConfig` 字段）。如果它和装配实际引用的 `config` 不一致，构建时会提示，插件不会擅自切换配置。

## 论文依据与边界

依据 MATTERIX（Darvish 等，DOI 10.1038/s43588-025-00924-4）Methods 中的 Asset generation：3D 模型转换为 USD 后，要补充质量等物理属性；关节型资产由关节描述生成。这个插件只负责从 CAD 中提取这些依据，不生成 USD。几何仍然由 HOOPS 转换，关节和碰撞由这边根据 JSON 构建。配合描述的是约束，不等于驱动参数：电机推力、速度和行程中没有限制配合的部分，仍需要型号手册或你来确认。

## 当前验证状态

已在 SolidWorks 2023 上编译、安装并实际导出过一台约 1000 个零件、1700 条配合的移液工作站。导出的位姿和 HOOPS 转换结果逐件一致（误差 <1e-5 mm），并成功推导出 47 个关节。其他 SolidWorks 版本没有测试过；如果编译报错，把 `build.bat` 的输出贴回来。
