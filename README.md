# 总平面图：图片 → CAD（DWG）

`input/site_plan.webp` 中的线稿已矢量化，并按真实尺寸缩放：
**红线 = 19.5 m**。

## 输出文件

| 文件 | 说明 |
|---|---|
| `output/site_plan.dwg` | **AutoCAD 2018 格式 DWG（AC1032）**，即 AutoCAD 2018–2025 使用的原生格式，推荐用 AutoCAD 2025 打开 |
| `output/site_plan.dxf` | 同一图形的 DXF 版本（备用，AutoCAD 2025 可直接打开） |
| `output/site_plan_R2000.dwg` | 旧版 R2000 DWG（LibreDWG 生成，仅作兼容备用） |
| `output/preview.png`   | DWG 回读后渲染的预览图 |

- 单位：**毫米**（INSUNITS = 4），1 个图形单位 = 1 mm，原点位于图片左下角。
- 比例：红线在图中约 215.7 px → 约 90.4 mm/px，整张图约 151.0 m × 85.1 m。
- 图层：
  - `LINEWORK`（白/黑）：全部线稿，约 15,000 条多段线
  - `RED_LINE`（红）：19.5 m 参考线（`LIST` 命令显示长度 = 19500）
  - `ANNOTATION`（绿）：“19.5m” 标注文字和图框

说明：线条由像素图自动提取（骨架化提取中心线 + 折线简化）。
因此精度受原图分辨率限制，误差约为 ±1 像素（约 ±0.1 m）。
树冠、作物行等仍是手绘风格的折线，不是规则的圆或直线。

## 重新生成

```bash
pip install opencv-python-headless ezdxf scikit-image pillow numpy
python3 tools/image_to_cad.py input/site_plan.webp output/site_plan.dxf \
    --red-length-m 19.5 --geom site.geom
# AutoCAD 2018-2025 DWG (needs .NET 8 SDK; uses ACadSharp from NuGet)
dotnet run -c Release --project tools/GeomToDwg -- site.geom output/site_plan.dwg
dotnet run -c Release --project tools/GeomToDwg -- --check output/site_plan.dwg

# Optional R2000 DWG via LibreDWG 0.13 (built from source)
cc -O2 tools/geom2dwg.c -I<libredwg>/include -L<libredwg>/build -lredwg -lm -o geom2dwg
./geom2dwg site.geom output/site_plan_R2000.dwg
```
