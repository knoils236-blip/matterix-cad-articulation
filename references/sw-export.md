# SolidWorks 导出（matterix-sw-export-v1）

插件源码在 `assets/solidworks_addin/`。安装、构建步骤见其中的 README_ZH.md：在 Windows 上用 .NET Framework 4 自带的 csc 编译，引用 SolidWorks 的 `api\redist` 互操作 DLL，生成的安装 exe 需要管理员权限。Linux 这边无法编译，因为缺少达索的互操作 DLL。插件只读模型，不修改。

## 顶层结构

`components`、`mates`、`parts`，单位全部为 SI。

- **component**：
  - `name`：实例完整路径，如 `子装配-1/零件-1`，与 HOOPS 的 `displayName` 路径一一对应；
  - 另有 `parent`、`path`（零件文件）、`config`、`isAssembly`、`suppressed`、`visible`、`flexible`、`transform`。
- **mate**：`feature`、`featureType`（MateCoincident / MateConcentric / MateDistanceDim / MateParallel / MateLimitDistanceDim / MateWidth / MateSymmetric / MateCoordinate / MateLock / MateSlot …）、`owner`（所属子装配实例，顶层为空串）、`suppressed`、`dimensions`、`entities[{component, refType, params}]`，限位配合另有 `minimum` / `maximum`。
- **part**：以（`path`, `config`）为键，含 `material`、`density`、`mass`、`volume`、`centerOfMass`、`inertiaAtCom`（3×3，零件坐标系、质心处）、`properties` / `configProperties`（自定义属性，如 材料 / 型号）。

## 容易读错的事实（在移液站数据上核实过）

- **`transform` 的约定**：`ArrayData`，元素 0–8 是旋转 R（按行排列），9–11 是平移（m），采用行向量约定：`x_world = x_local @ R + t`。惯量换到世界系用 `Rᵀ I R`。
- **实体 `params` 的坐标系**：`[点 xyz, 方向 xyz, 半径]`，表达在**所属子装配（owner）的坐标系**里，不是世界系。
- **`refType` 编码**（从数据推断）：
  - 0：点；
  - 1：轴或直线；
  - 2：面（r>0 为圆柱，否则为平面）；
  - 3 / 4：基准面；
  - 11 / 25：坐标系。
- **自身基准面**：实体的 `component` 如果不在 components 里（例如等于装配文件名），指的是 owner 装配自身的基准面。顶层装配名指整机原点。
- **`fixed` 不可靠**：所有组件的 `fixed` 都是 false，不能用它判断接地。接地关系来自配合和 overrides。
- **限位配合的 min/max**：`minimum` / `maximum` 是**相对当前值的变化量**，不是绝对距离；`max−min` 等于模型行程。
- **位姿来源**：柔性子装配在 SolidWorks 中求解后的位姿，可能和别的转换器不一样。HOOPS 输出与本插件的 `transform` 在移液站上完全一致（误差 <1e-5 mm），`build_articulated` 会逐件断言这一点。
- **质量属性**：按零件当前激活配置计算，配置记录在 `massConfig`。没设材料的零件按 1000 kg/m³ 计算；有少数零件密度为 0，质量也为 0。常见情况是自定义属性 `材料` / `材质` 里写了真实材料，这时用 `--density` 修正。
- **插件行为**：导出前会还原轻化零部件，大装配需要等几分钟。
