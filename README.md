# GreenShip —— 内河船舶绿色航行智能评估与优化平台

GreenShip 是一个可输入真实船舶运行参数的绿色航行决策平台，支持柴油、纯电、混合动力三方案的能耗、成本、碳排放和运输效率比较，并使用 SciPy 差分进化算法完成分航段航速优化。

## 核心功能

- 船舶、航线、水流、水深、电池与能源参数输入
- 三种动力方案实时计算与绿色方案推荐
- 电池 SOC、安全余量和续航风险分析
- 成本、排放、能源结构与 Green Score 可视化
- 差分进化算法分航段智能航速优化
- 航行记录持久化、检索与 CSV 导出
- 完整中文输入校验、移动端适配

## 本地运行

建议使用 Python 3.11 或更高版本。

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

浏览器访问 `http://127.0.0.1:5000`。

## API

- `POST /api/calculate`：计算三种能源方案
- `POST /api/optimize`：运行差分进化航速优化
- `GET /api/energy-prices`：读取能源价格
- `POST /api/save-voyage`：保存航行记录
- `GET /api/history`：读取航行历史
- `GET /api/export/csv`：导出 CSV

## 部署到 Render

仓库已包含 `render.yaml` 和 `Procfile`。在 Render 中连接 GitHub 仓库并创建 Web Service 即可；平台会自动安装依赖并用 Gunicorn 启动服务。

> 当前航行记录保存到 `data/voyages.json`。本地运行可长期保留；免费云实例的本地文件系统可能在重启后重置。正式生产环境建议替换为 PostgreSQL。

## 模型说明

功率模型综合基础负载、航速立方关系、载重、浅水和逆流修正。电力与柴油排放因子集中配置在 `models/carbon_model.py`，能源模型位于 `models/energy_model.py`，优化器位于 `models/optimizer.py`，方便后续接入实测数据和调整研究参数。
