# Remotion 动效预设

| 编号 | type | 默认 preset | 参考帧 | 默认时长 |
|---|---|---|---:|---:|
| 1 | `dynamic_shrink` | `reference_first_v2` | 0..10 | `10/30s` |
| 2 | `bottom_rise` | `reference_second_v1` | 0..15 | `15/30s` |
| 3 | `perspective_settle` | `reference_third_v3` | 0..16 | `16/30s` |
| 4 | `flash_stretch` | `reference_fourth_v1` | 0..13 | `13/30s` |
| 5 | `page_curl` | `webgl_page_curl_v1` | 0..26 | `26/30s` |

## dynamic_shrink / 动感缩小

### reference_first_v2（默认）

V2 来自“参考视频第一动效-动感缩小”的逐帧校准。它保留 V1 的正式运动轨迹，重点修复前 0..4 帧的发白、背景穿透、采样断层和多重硬边。

默认视觉参数：

- 参考帧：`0..10`，基准帧率 `30fps`；
- 正式缩放：`2.01 → 1.00`；
- 正式 Y 偏移：`-125 → 0`，按目标素材高度相对 `838px` 缩放；
- 普通模糊：`2.8px → 0`，按画布宽度相对 `720px` 缩放；
- 拖影：`1 → 0`；
- 快门采样范围：`4.2 → 0` 个参考帧；
- 连续预滚：`-4..-1` 参考帧，仅供快门采样；
- 亚帧采样层：默认 `72`，允许 `12..96`；
- 默认持续时间：`10/30s`，约 `0.333s`；
- 第 10 个参考帧后停止拖影采样，只渲染稳定主图。

V2 加工方法：

1. 使用离散关键帧保留 `scale`、`offsetY`、`blur`、`trail` 和 `shutter` 的逐帧节奏。
2. 将 `-4..-1` 帧补成连续的更大近景，避免第 0 帧负时间采样全部被钳在 `2.01x`。
3. 对每层使用格中心采样 `u=(i+0.5)/samples`，采样时间为 `frame + (u-0.54)*shutter`，轻微偏向过去以保留向外拖尾。
4. 使用 Hann 权重 `sin(πu)^1.35`，使快门两端平滑降为 0。
5. 将所有权重除以权重总和，拖影总曝光为 `0.82*trail`，避免采样层数改变画面亮度。
6. 先绘制完全不透明的主图，再覆盖归一化拖影；不得降低主图透明度。
7. 当 `trail=0` 时跳过所有采样层，稳定阶段只渲染一层主图。

时间线事件：

```json
{
  "name": "金额利益点",
  "path": "material.png",
  "kind": "image",
  "start": 1.0,
  "end": 4.0,
  "layout": {
    "width": 506,
    "height": 838,
    "x": 107,
    "y": 215,
    "origin_x": 253,
    "origin_y": 419,
    "border_radius": 17
  },
  "effect": {
    "type": "dynamic_shrink",
    "preset": "reference_first_v2",
    "duration": 0.333333,
    "samples": 72
  }
}
```

可配置字段：

- `duration`：重定时完整参考曲线，必须大于 0 且不超过事件可见时长；
- `samples`：V2 允许 `12..96`，默认 `72`；
- `layout.origin_x/origin_y`：缩放中心，默认目标素材中心；
- `layout.border_radius`：目标素材裁切圆角，默认按参考素材宽度换算。

### reference_first_v1（兼容）

V1 保留旧的 48 层对称采样算法，负时间会钳在第 0 帧。仅在重现旧输出或兼容旧时间线时使用；新任务一律使用 V2。V1 的 `samples` 允许 `1..96`，默认 `48`。

中文 `动感缩小` 可作为 `effect.type`；渲染前统一归一化为 `dynamic_shrink`。

## bottom_rise / 底部上冲回正

### reference_second_v1

来自原视频 F58..F73。素材保持最终宽高不变，仅改变 Y 偏移和前两帧透明度：

- 参考 Y 偏移：`[645,575,510,444,377,312,251,182,117,102,67,41,21,8,1,0]`，按素材高度相对 `838px` 缩放；
- 透明度：`[0,.332,.664,.996,1...]`；
- 第 0 帧为空场，第 15 帧落在最终 `layout.x/y`；
- 默认时长 `15/30s`，不使用快门采样。

```json
"effect": {
  "type": "bottom_rise",
  "preset": "reference_second_v1",
  "duration": 0.5
}
```

中文 `底部上冲回正`、`底部上冲`、`第二动效` 可作为别名。

## perspective_settle / 透视翻转回正

### reference_third_v3

采用第三动效最终 V3：连续负帧预滚、72 层归一化拖影、动态右侧释放和俯仰透视。

- 起始状态：`scale=1.52`、`rotateX=-18°`、`rotateY=36°`、X 偏移 `66px`；
- 透视距离：参考 `880px`，按素材宽度相对 `506px` 缩放；
- 快门范围：`7.5 → 0` 参考帧，连续预滚起点 `-4`；
- 右边界参考坐标：帧 `[0,1,2,7,8,9,10,12,16]` 对应 `[623,661,671,671,664,654,644,628,623]`；
- 默认时长 `16/30s`，`samples=72`，允许 `12..96`。

```json
"effect": {
  "type": "perspective_settle",
  "preset": "reference_third_v3",
  "duration": 0.533333,
  "samples": 72
}
```

中文 `透视翻转回正`、`第三动效` 可作为别名。

## flash_stretch / 白闪拉伸回正

### reference_fourth_v1

来自原视频 F174..F187。使用逐帧外框、曝光、对比度与模糊曲线，并在第 0 帧增加左右独立白色拖影。

- 第 0 帧主框参考坐标：`(127,144)..(588,1073)`；
- 第 1–5 帧逐步恢复横向宽度、纵向拉伸和内容对比度；
- 滤镜顺序固定为 `blur → contrast → brightness`，避免 `contrast(0)` 把白闪压成灰色；
- 第 13 帧稳定在最终布局；默认时长 `13/30s`，不使用采样参数。

```json
"effect": {
  "type": "flash_stretch",
  "preset": "reference_fourth_v1",
  "duration": 0.433333
}
```

中文 `白闪拉伸回正`、`白闪拉伸`、`第四动效` 可作为别名。

## page_curl / 卷页翻入回正

### webgl_page_curl_v1（默认）

使用 `@vysmo/transitions` WebGL2 网格，从接近完全收卷的状态连续展开到最终布局。旧的纵向切片方案已移除。

- 128×32 细分网格，使用真实顶点弯曲、正反面和深度遮挡；
- Shader 进度 `0.985 → 0`，使用有界 cubic 缓动，默认时长 `26/30s`；
- Canvas 在素材四周增加约 `18%` 安全边距，卷曲超出原图边界时不得被裁断；
- 正面使用原图片；背面再次采样原图片，依靠反向网格自然形成镜像；
- 默认 `back_texture_strength=0.92`，允许 `0..1`；
- destination plane 保持透明，composite 模式露出底层视频，alpha 模式只保留卷页和半透明阴影；
- 素材按 `layout.border_radius` 预裁切，稳定后切换为普通单层图片；
- 旧 preset 名 `reference_fifth_v1` 仅作为输入兼容别名，实际统一归一化为 `webgl_page_curl_v1`；旧 `slices` 字段会被忽略。

```json
"effect": {
  "type": "page_curl",
  "preset": "webgl_page_curl_v1",
  "duration": 0.866667,
  "back_texture_strength": 0.92
}
```

中文 `卷页翻入回正`、`卷页翻入`、`第五动效` 可作为别名。

## 通用缩放规则

- X 坐标和宽度按最终素材宽度相对参考 `506px` 映射；
- Y 坐标和高度按最终素材高度相对参考 `838px` 映射；
- 参考最终位置为画布 `720×1280` 中的 `(107,215)`；实际渲染统一映射到事件 `layout.x/y/width/height`；
- 改变 `duration` 时重定时完整参考曲线，不截断曲线尾部。
