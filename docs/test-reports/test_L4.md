# L4 测试报告 · 大规模压力

- 验收标准：15 分钟内出解
- 数据目录：`/Users/tangmengzhang/Downloads/2026/OR_Course_2026_SO/Zen老师大作业/mip_course/data/large`

## 求解结果

| 指标 | 值 |
|---|---|
| status | FEASIBLE |
| solver | 构造+ALNS(900s) |
| makespan | 2120 |
| tardiness | 53169 |
| completion | 156014 |
| objective | 53169.0 |
| solve_time_s | 900.0020129680634 |
| num_machines | 20 |
| num_orders | 200 |
| λ | [0.0, 1.0, 0.0] |

## 约束验证（自动）

✓ 全部通过：每订单恰一机台、机器-配方兼容、NoOverlap、切换+清理时间、延误/完工/目标一致性。

## 结论

**✓ 通过** （status=FEASIBLE，验证通过）
