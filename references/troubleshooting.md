# 排错与实测过的坑

## 静态资产

`build_static.py` 生成的 `<Name>.usdc` 本身就能作为静态设施使用（对应 MATTERIX 论文 Asset generation 里的 prim 类，即“仅碰撞的静态对象”）：

```python
@configclass
class STATION_STATIC_INST_CFG(MatterixStaticObjectCfg):
    prim_path = MatterixStaticObjectCfg().prim_path + "_Equipment"
    usd_path = "<abs path>/<Name>.usdc"
    semantic_tags = [("class", "<class>")]
```

自己写 Matterix 环境做验证时，`MatterixBaseEnvCfg` 必须设置 `scene = InteractiveSceneCfg(num_envs=2, env_spacing=4.0)`，同时设 `record_path = None`。没有 `MATTERIX_PATH` 时会在导入阶段就失败。

PhysX 会对大三角面报 “triangles are too big” 警告。对静态碰撞影响不大，可以记录下来不处理。

## Isaac Lab / PhysX（Isaac Lab 3.0、Isaac Sim 6 上实测）

| 症状 | 原因 | 处理 |
|---|---|---|
| `NotImplementedError: ... does not have the RigidBodyAPI applied ... fixed joint` | 用了 `fix_root_link=True`，但 ArticulationRootAPI 加在普通 Xform 上 | 把 ArticulationRootAPI 加到 `base` 刚体上（`build_articulated` 已这样做） |
| `Collisions are supported currently only in one collision group` / `Replication of this type is not supported`，外部物体直接穿过资产 | 资产里自定义了 CollisionGroup；Isaac Lab 已经用碰撞组隔离各环境 | 不用碰撞组，改用逐 link 的 FilteredPairs |
| 加了 FilteredPairs，门、滑台等仍卡在 0 位 | FilteredPairs 挂在 articulation 根上，只对根 link 生效 | 每个运动 link 各自过滤自己扫掠盒内的静态碰撞体 |
| 竖直轴直接掉到行程下限 | 没有 DriveAPI / maxForce，驱动不出力 | USD 中写 linear drive 和 maxForce；读回 `joint_stiffness`、`joint_effort_limits` 核对 |
| 两个关节偏差几毫米、方向相反，像被弹簧拽着 | 被动件被独立驱动，被它的安装点拉住（例：气弹簧约 550 N） | 先把它的目标设成随主关节变化做对照实验；确认后按实机焊接，减去这个自由度（见 kinematics.md） |
| 部分关节不动，`--no-link-collisions` 下却全部到位 | 内部接触，即 link 与没过滤到的碰撞体接触 | 检查扫掠盒是否覆盖了全部祖先关节的行程；检查碰撞体是否在 `Geometry` 之外 |
| `GPU-compatible convex hull could not be built because of oblong shape` | 细长件的凸包退回 CPU 碰撞 | 可以忽略；如果需要粒子或可变形体与它交互，就换近似方式 |
| `rig parts not in the static USD` | 手写 rig 的零件名和 USD 里的显示名路径不一致（少了顶层前缀、同名件没带 `#2`） | 从 `list_components.py <static.usdc>` 的输出里复制零件名 |
| 手写的旋转关节朝反方向开，或绕着错误的位置甩 | `axis` 方向反了；`anchor` 不在转轴上 | 轴取反或交换 lower/upper；anchor 取铰链边上的点（见 manual-rig.md） |
| HDF5 报错，信息莫名其妙 | 两个 Matterix 进程同时运行，抢 `datasets/dataset.hdf5` 的锁 | 串行运行 |

## 几何与坐标

- HOOPS 设置：`upAxis=eZup`；`instancingStyle=eNone`（每个实例单独一个 prim，零件才能挪到各自的 link 下）；`filterStyle=eHide`（隐藏件保留、但不可见）；`convertMetadata=True`（保留 `displayName`，这是 USD prim 和导出 JSON 之间的唯一对应）。
- `build_articulated` 断言 CAD 坐标系和 USD 坐标系之间只差平移。如果断言失败，常见原因是源文件是 Y-up，HOOPS 做了旋转；这时需要在脚本里加上这个旋转，不能跳过断言。
- 运动零件移入 link 时会保留有效可见性：被父装配隐藏的零件，移动后仍保持隐藏。
