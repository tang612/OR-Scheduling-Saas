# L1 测试报告 · 玩具用例 · 手工可验证

- 验收标准：必须给出正确解
- 数据目录：`/Users/tangmengzhang/Downloads/2026/OR_Course_2026_SO/Zen老师大作业/mip_course/data/toy`

## 求解结果

| 指标 | 值 |
|---|---|
| status | OPTIMAL |
| solver | CP-SAT |
| makespan | 90 |
| tardiness | 82 |
| completion | 254 |
| objective | 82.0 |
| gap | 0.0 |
| solve_time_s | 0.008476018905639648 |
| num_machines | 3 |
| num_orders | 5 |
| λ | [0.0, 1.0, 0.0] |

## 约束验证（自动）

✓ 全部通过：每订单恰一机台、机器-配方兼容、NoOverlap、切换+清理时间、延误/完工/目标一致性。

## 结论

**✓ 通过** （status=OPTIMAL，验证通过）
