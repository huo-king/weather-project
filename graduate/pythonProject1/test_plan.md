测试报告（可直接作为论文/答辩材料的“系统测试 + 质量自检 + 预测评估”章节）

一、测试环境
- 操作系统：Windows
- 后端：FastAPI + Uvicorn
- 数据库：MySQL
- 前端：HTML/CSS/JS + ECharts

二、功能测试用例（核心功能验收）

1. 用户系统
1.1 注册
- 用例：输入合法 username/email/password 注册
- 预期：返回 200，users 表新增记录
- 异常：重复邮箱/用户名，返回 400

1.2 登录
- 用例：正确邮箱+密码登录
- 预期：返回 token，/api/users/me 能正常返回用户信息
- 异常：密码错误/邮箱不存在，返回 401

1.3 常用辖区
- 用例：PUT /api/users/preferred_areas 写入 1~3 个辖区
- 预期：GET 返回一致，前端下拉框可切换区域
- 异常：写入空/重复/超过3个，后端自动去重截断

2. 历史查询（保留近30条）
- 用例：连续点击“应用筛选”超过30次（或脚本调用 POST /api/users/history）
- 预期：GET /api/users/history 最多返回 30 条
- 前端：登录后“历史查询”面板可查看，点击可恢复筛选

3. 收藏（按图表收藏）
- 用例：点击每张图表标题旁的 ★ 收藏按钮
- 预期：/api/users/favorites 列表出现 chart_type + area；再次点击可取消
- 权限：未登录点击 ★ 应提示登录

4. 社交互动（按区域统计）
- /api/social/stats：未登录可访问，active=false
- /api/social/toggle：需登录；重复点击可切换

5. 数据查询与可视化
5.1 /api/trend/aqi + granularity
- 用例：granularity=day/week/month
- 预期：返回 x/y；周/月切换不报错

5.2 /api/trend/temp + granularity
- 用例：granularity=day/week/month
- 预期：返回 x/max/min

5.3 /api/export/weather_data.csv
- 用例：带 area/start/end
- 预期：浏览器下载 csv；中文文件名可用（若浏览器不支持会 fallback）

6. 手动采集
- 用例：POST /api/admin/scrape_now
- 预期：返回 ok/inserted/total_scraped；MySQL weather_data 新增数据

7. 预测模块
7.1 高级分析预测（GET /api/analysis/forecast_7d）
- 预期：返回 forecast（包含 p10/p50/p90），前端展示区间带 + 等级/提示/置信度

7.2 自定义输入预测（POST /api/predict/aqi_7d）
- 用例：输入 area + meteo_7d(7天)
- 预期：返回 forecast（包含 level/color/tip/confidence）

三、质量自检（新增）

A) 爬取数据 vs 网站一致性抽检
目的：自检测数据库中爬取的数据与 2345 天气网页面展示是否一致。
方法：随机抽样 N 条记录（默认 5 条），从网站重新解析对应日期记录并对比。
判定：
- aqi 必须一致
- 温度允许 ≤0.5℃ 误差（考虑页面格式/四舍五入）

B) 预测 vs 实际误差评估（不超过70%）
目的：直观看到预测数据与现实数据的对比差距。
方法：对最近30天做滚动回测（walk-forward），预测下一天 P50 与真实 AQI 对比。
指标：MAPE（平均相对误差）
判定：MAPE <= 0.7（即误差不超过70%）则通过。

四、性能测试建议

1) 压测工具
- 推荐：wrk / hey / locust

2) 关键接口建议压测
- /api/trend/aqi（广州/单区，day/week/month）
- /api/compare/aqi
- /api/analysis/forecast_7d

3) 建议指标
- QPS
- P95/P99 响应时间
- 错误率
- MySQL 慢查询

五、结论
- 系统功能覆盖：采集、存储、查询、可视化、预测、用户交互
- 质量自检覆盖：数据一致性抽检 + 预测误差阈值评估
- 风险点：采集受目标站点结构变化影响；预测受未来气象输入质量影响
