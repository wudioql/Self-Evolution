# 歌 #3《不好惹》· 方向 brief（v0.1，2026-11-08）

- 用途：给自己的词、曲、编曲、封面与视频定一个判断锚，不写进执行层
- 定稿人：本人 2026-11-08 确认选 C「江湖毒舌」
- 原曲：阿萨Aza《不好惹》（《大王饶命》OP，2:58）；本首为原创，只偷和声骨架与结构，旋律与词自写

## 1. 一句话方向

把「不好惹」往江湖气走：像个和气但不吃亏的茶馆掌柜，笑着说话，话里带刺。

## 2. 三个形容词

江湖 · 硬气 · 带笑

## 3. 人设与口吻

- 看起来好说话，实际一句都不让。
- 句子短，夹一句大白话；不解释、不吵架、不卖惨。
- 怼的对象是「事」和「场面」，不是具体的人。

## 4. 三个已挑手法的落点

| 手法 | 落在哪 | 具体做法 |
|---|---|---|
| 说话感（人声层） | W11 人声（11-19） | 副歌前后各留一句半说半唱，不飙高音；SV 与自唱都能做 |
| 强烈律动 | W12 编曲（11-20） | 鼓与贝斯抢先，人声跟在后面，不靠人声顶力度 |
| 交叉拼贴 | 已在 9-1 动机兑现 | 音高与节奏分别取自《Lemon》与《うっせぇわ》，不整体照搬 |

- 调性沿用动机现状：A 小调五声（A C D E G），不改调。
- `motif.mid` / `motif.song` 只留本地；本文件是文字说明，可公开。

## 5. 出图方案（14 次生成 · 16 张成品）

### 5.1 清单

| 组 | 生成张数 | 比例 | 用途 | 必需 |
|---|---|---|---|---|
| 封面候选 | 4 | 16:9 | 挑 1 定稿 | 是 |
| 封面派生 | 2 | 1:1（扩图）/ 9:16 | 播放器方图 / 竖版备用 | 方图看平台 |
| 歌词图 | 6 | 16:9 | 剪映里按段落切换底图 | 是 |
| 空镜 | 4 | 16:9 | 间奏、过渡 | 是 |

数量可以多，约束不是张数，是一致性与挑图时间。

### 5.2 风格块（每张逐字复用，一字不改）

```
flat graphic illustration, bold hand-inked outlines, aged rice-paper cream background,
woodcut and paper-cut texture, slightly off-register print feel, limited 3-color palette
(ink black, warm amber, one vermilion accent), bright even high-key lighting,
no dramatic shadows, clear readable shapes, warm muted palette
```

- 三色卡：墨黑 + 暖黄（主调）+ 朱红一点，**米白纸底作为第四色负责提亮**。
- 固定：粗墨线、平涂、印刷错版感、无强阴影、无景深、白天光。
- 版式：主体占画面 40–60%，四周留米白纸边；不做满、不压暗四角、不做夜景。
- 每次只换主体、动作、道具。
- 为什么不用夜景电影感：这首歌是「硬气带笑」的江湖毒舌，要平面、明亮、有版式感；暗调写实会把它压成另一种情绪。

### 5.3 元素

- 必现 5：旧木招牌（无字或模糊笔迹）、墨色人物剪影、冒热气的茶壶或碗、灯笼（白天也点着）、大面积米白留白。
- 可选：竹椅、门帘、折扇、茶碗、猫、算盘、朱红印章（每张最多加 1–2 个）。
- 禁止：文字字母、血腥、持械、真人面孔、机台厂区、logo、高饱和、霓虹赛博、**写实照片感、3D 渲染感、强烈明暗对比、夜景黑底**。
- 一致性硬招：把第一张满意的当「母版」，后续用 Qwen-Image-2.1 把它当参考图（最多 10 张参考），比只改提示词稳。
- 母版怎么选：不是选「最好看」，是选**最标准**——三色卡没跑、纸底干净明亮、必现元素都在、构图普通可复制；戏剧化 / 特殊构图的不要当模板。复制一份到 `_refs/ref-master.png`，原图留在 `cover/`。
- 参考图只管风格、不管构图：prompt 里保留完整风格块，并写明 same visual style, different composition/scene；否则十几张会长得一样。

### 5.4 比例与派生

| 比例 | 怎么来 | 说明 |
|---|---|---|
| 16:9（主） | 1344×768 生成 → 放大到 1920×1080 | B 站封面就用这个 |
| 1:1 | **扩图**（上下补），不裁 | 16:9 裁成 1:1 只砍左右，构图会废 |
| 9:16 | 按竖版直接重生成 | 竖版是构图重排，扩边会很假 |

- 出 16:9 时按「中央方形安全区」构图（主体完整落在中央 1:1 内，四角只放可丢元素），以后要方图在安全区内裁就无损，超出再用扩图补。
- 方图不是必须的：只发 B 站就跳过 1:1。

### 5.5 提示词

结构固定：`[风格块] + subject / action / setting / props`

封面（16:9）：
```
[风格块] + a wooden hanging signboard with faded ink lettering at the left,
a lone shopkeeper in flat ink silhouette behind a tea counter, a steaming teapot,
bamboo chairs, one vermilion seal accent, wide cream paper space at the right, no text
```

6 张歌词图（各换一个变量）：
1. 招牌下的掌柜剪影，米白纸底（副歌一）
2. 门帘半掀，只露半个墨色身影（A 段）
3. 茶壶热气在纸底上升成一团（间奏）
4. 一张空竹椅 + 一盏点着的灯笼（留一口气）
5. 灯笼斜挂、朱红印章压角（副歌二）
6. 尾声：灯芯冒着烟，纸边留一大片空

4 张空镜：招牌特写 / 灯笼特写 / 门帘 / 茶碗与热气。

负词固定不变：
```
text, letters, chinese characters, watermark, logo, blood, weapon, gore,
real person face, modern machinery, factory, industrial equipment,
oversaturated, neon, cyberpunk, cluttered composition,
dark, underexposed, low-key lighting, night scene, black background,
photorealistic, realistic photo, 3d render, shallow depth of field, heavy shadows
```

暗调排查：如果还偏黑，先把负词里的 dark / low-key 留着，再在正词末尾加 `bright daylight, mid-cream paper base value, clearly visible subject`；仍偏暗就说明是模型默认风格，换无字构图用 Z-Image 出图。

参数固定：同分辨率、同步数、同一 seed 家族。带字封面换 MOSS-Image，加一行版式（标题放上方或右下）；字错用 Qwen-Image-2.1 局部改，改不动退回无字版后期叠字。

### 5.6 图片存放与命名

```
music-log/03-buhaore/images/
├── _refs/      母版与参考图（ref-master.png）
├── cover/      cover-a.png … → cover-final-16x9.png / -1x1 / -9x16
├── lyrics/     ly-1-zhangui.png … ly-6-deng.png
└── bts/        empty-signboard.png / empty-lantern.png / empty-curtain.png / empty-teacup.png
```

- 命名：`组-序号-短名.png`，定稿加 `final`，改版加 `-v2`，不覆盖旧版。
- **保留 PNG**：ComfyUI 的 PNG 内嵌工作流信息，转 JPG 会丢溯源；空镜需要压体积时另存 JPG 副本。
- **图片默认不进版本库**（体积大）：留本地即可；要留档只把封面定稿与说明纳入，提交前按仓库惯例授权。

## 6. 不做清单

- 不出现真机台、报警代码、厂区与产线信息，不出现任何工作标识。
- 不做血腥暴力、不做可识别真人、不模仿原曲封面。
- 不装新工具、不定稿多套风格：封面 1 套主轴 + 2–3 张试片即可。

## 7. 沿用的验收

- 旋律自写（非扒）；有封面、视频、歌词字幕；本人愿意转发给朋友。
- 日期与状态以 `progress/plan90.json` 为准，本文件只记方向。
