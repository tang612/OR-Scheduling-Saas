# L2 测试报告 · 边界用例 · 高不可切换比例

- 验收标准：不崩溃，null 正确处理
- 数据目录：`/Users/tangmengzhang/Downloads/2026/OR_Course_2026_SO/Zen老师大作业/mip_course/data/boundary`

## 求解结果

| 指标 | 值 |
|---|---|
| status | OPTIMAL |
| solver | CP-SAT |
| makespan | 570 |
| tardiness | 1270 |
| completion | 3058 |
| objective | 1270.0 |
| gap | 0.0 |
| solve_time_s | 24.701187133789062 |
| num_machines | 4 |
| num_orders | 12 |
| λ | [0.0, 1.0, 0.0] |

## 约束验证（自动）

✓ 全部通过：每订单恰一机台、机器-配方兼容、NoOverlap、切换+清理时间、延误/完工/目标一致性。

## 结论

**✓ 通过** （status=OPTIMAL，验证通过）
