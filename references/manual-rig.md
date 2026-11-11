# 手写 rig：没有 SolidWorks 导出时，或要补配合推不出的关节

`build_articulated.py` 不带 `--export` 时，读一份手写的 `rig.json`。适用于：

- 源文件是 STEP / IGES / 其它 CAD，或用户装不了 SolidWorks 插件；
- 机构是旋转的（铰链门、转台、旋转电爪）。配合推导目前只出移动关节。

在移液站静态 USD 上实测过：一个升降门（移动）加一扇钣金后门（旋转），Matterix 双环境验收通过，误差 0.47 mm / 2e-6 rad。

和配合推导相比，这条路线没有“配合”这层证据，关节表完全来自人。所以每个关节的轴、行程、归属都要有出处（说明书、型号手册、用户口述），写进 README 的关节表；出处不够就问用户，不要目测凑数。

## 步骤

1. 照常做第 1 步得到静态 USD。
2. 看零件树，找出每个机构的运动件：

   ```bash
   python scripts/list_components.py <out>/<Name>.usdc --depth 4 [--under 前缀] [--grep 叶子名子串 ...]
   ```

   每行是 `零件名  centre [x y z]  size [dx dy dz]`，单位 mm，坐标系就是静态 USD 的坐标系（Z 朝上，原点在地面中心）。零件名是 `Geometry` 下的显示名路径；同名兄弟节点从第二个起带 `#2`、`#3` 后缀。
3. 写 `rig.json`（格式见下），构建，再按 SKILL.md 第 4、5 步填 cfg、验收：

   ```bash
   python scripts/build_articulated.py --rig <out>/rig.json --static <out>/<Name>.usdc --out <out>/<Name>Articulated.usdc
   ```

## rig.json 格式

```json
{
  "links": [
    {"name": "link_slide", "mass": 2.4, "parts": ["asm/Slide-1/Carriage-1", "asm/Slide-1/Adapter-1"]},
    {"name": "link_finger_l", "density": 2700, "parts": ["asm/Gripper-1/Finger-1"]},
    {"name": "link_door", "mass": 8.0, "parts": ["asm/Enclosure-1/Door-1"]}
  ],
  "joints": [
    {"name": "slide", "type": "prismatic", "parent": "base", "child": "link_slide",
     "axis": [1, 0, 0], "anchor": [0.0, 0.12, 0.35], "lower": 0.0, "upper": 0.3},
    {"name": "finger_l", "type": "prismatic", "parent": "link_slide", "child": "link_finger_l",
     "axis": [0, 1, 0], "anchor": [0.05, 0.12, 0.30], "lower": 0.0, "upper": 0.01},
    {"name": "door", "type": "revolute", "parent": "base", "child": "link_door",
     "axis": [0, 0, 1], "anchor": [-0.464, -0.504, 1.222], "lower": -1.5708, "upper": 0.0}
  ]
}
```

- **parts**：`list_components.py` 打出的零件名。写子装配的名字，整个子装配一起动；如果它里面某个零件属于另一个 link（滑台子装配里的夹爪手指），把那个零件单独列进它自己的 link 即可，脚本会把它从父 link 里拿掉。没列进任何 link 的几何留在固定基座上。
- **mass / density**：每个 link 必须给其中一个。`mass`（kg）来自型号手册或称重；`density`（kg/m³）来自材料。质心和惯量由 PhysX 从凸包碰撞体算。凸包比实体大（凹腔被填实），所以空心件、钣金件给 `mass` 更准，给 `density` 会偏重。
- **axis / anchor**：静态 USD 坐标系，米。`axis` 是单位向量；移动关节的 `anchor` 取运动件上任意一点即可，旋转关节的 `anchor` 必须在转轴上（铰链门取铰链边：门的 centre 沿宽度方向挪半个 size）。
- **lower / upper**：0 是 CAD 保存位姿。移动关节用米，旋转关节用**弧度**。正方向由 `axis` 决定（旋转按右手定则），拿不准就先构建、在验收 JSON 的 `reached` 里看方向，或渲染预览。
- **parent**：`base` 或另一个 link 的名字。串联机构（X 上挂 Z、Z 上挂夹爪）按实机承载关系写。
- 对称夹爪：两指各写一个关节，Matterix 侧同时给目标；要严格联动就在 cfg 里用同一个 action 驱动两个关节。

## 验收时注意

- `validate_articulated.py` 对旋转关节同样适用，这时误差和 `--tol` 的单位是弧度（JSON 里字段名仍叫 `maxJointErrorM`）。
- 旋转 link 的碰撞过滤范围，是以 `anchor` 为中心、能扫到的球的外接立方体，比较保守：门附近的静态碰撞体都不会挡它，但也意味着它不会被门框挡住，开合范围只靠 `lower/upper`。
- 报告里 `source` 为 null、`swToStationShift` 为 0 是正常的：没有 CAD 导出可对照。
