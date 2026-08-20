"""将单机加权完工时间数学模型渲染为高可读性 PNG 图片（matplotlib mathtext）。
中文标签 + 数学公式混排；mathtext.fontset='stix' 使数学符号接近 LaTeX 排版。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

# ---- 中文字体注册（macOS 系统字体）----
for f in ["/System/Library/Fonts/STHeiti Medium.ttc",
          "/System/Library/Fonts/Hiragino Sans GB.ttc"]:
    try:
        fm.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["STHeiti", "Hiragino Sans GB", "Heiti SC", "sans-serif"]
plt.rcParams["mathtext.fontset"] = "stix"   # 数学符号接近 LaTeX
plt.rcParams["axes.unicode_minus"] = False

fig = plt.figure(figsize=(13.5, 11.5), dpi=200)
ax = fig.add_axes([0, 0, 1, 1])
ax.axis("off")

y = 0.985
step = 0.058

def line(txt, size=15, weight="normal", color="#1a1a2e", dy=None):
    global y
    ax.text(0.03, y, txt, fontsize=size, fontweight=weight, color=color,
            va="top", ha="left", linespacing=1.9)
    y -= (dy if dy else step)

# ---- 标题 ----
line(r"单机加权完工时间最小化  ·  数学模型", size=23, weight="bold", color="#4a6cf7", dy=0.075)
line(r"问题类型: $1 \, \| \, \cdot \, \| \, \sum w_j C_j$（P 类，WSPT 可解析求解）", size=13, color="#666", dy=0.055)

# ---- 集合 ----
line(r"【集合】", size=16, weight="bold", color="#4a6cf7", dy=0.05)
line(r"$\mathcal{J} = \{1, 2, 3\}$  作业集合；   $\mathcal{K} = \{1, 2, 3\}$  加工位置集合", size=16)

# ---- 参数 ----
line(r"【参数】", size=16, weight="bold", color="#4a6cf7", dy=0.05)
line(r"$p_j \in \mathbb{Z}_{+}$  作业 $j$ 的加工时间(小时):  $p_1 = 2,\ p_2 = 3,\ p_3 = 1$", size=16)
line(r"$w_j \in \mathbb{Z}_{+}$  作业 $j$ 的权重:  $w_1 = 3,\ w_2 = 1,\ w_3 = 2$", size=16)

# ---- 决策变量 ----
line(r"【决策变量】", size=16, weight="bold", color="#4a6cf7", dy=0.05)
line(r"$x_{jk} \in \{0, 1\}, \quad \forall j \in \mathcal{J},\ k \in \mathcal{K}$", size=16)
line(r"$x_{jk} = 1$ 当且仅当作业 $j$ 排在第 $k$ 个位置", size=14, color="#555")

# ---- 目标函数 ----
line(r"【目标函数】", size=16, weight="bold", color="#4a6cf7", dy=0.05)
line(r"(1)  $\min \ \sum_{k \in \mathcal{K}} C_k \sum_{j \in \mathcal{J}} w_j \, x_{jk}$", size=18, weight="bold")

# ---- 约束 ----
line(r"【约束条件】", size=16, weight="bold", color="#4a6cf7", dy=0.05)
line(r"(2)  $\sum_{k \in \mathcal{K}} x_{jk} = 1, \quad \forall j \in \mathcal{J}$      每个作业恰好占据一个位置", size=16)
line(r"(3)  $\sum_{j \in \mathcal{J}} x_{jk} = 1, \quad \forall k \in \mathcal{K}$      每个位置恰好安排一个作业", size=16)
line(r"(4)  $C_k = \sum_{l=1}^{k} \sum_{j \in \mathcal{J}} p_j \, x_{jl}, \quad \forall k \in \mathcal{K}$", size=16)
line(r"     第 $k$ 位完工时间 = 前 $k$ 个作业加工时间累计", size=14, color="#555")

# ---- 数值声明与复杂度 ----
line(r"【数值声明与复杂度】", size=16, weight="bold", color="#4a6cf7", dy=0.05)
line(r"无 Big-$M$ 约束;  参数均为整数小时、量纲一致、无需缩放;  CP-SAT 整数域精确求解", size=14, color="#444")
line(r"复杂度:  $\mathcal{P}$ 类（WSPT / Smith 规则: 按 $p_j / w_j$ 升序加工即最优, 用于交叉验证）", size=14, color="#444")
line(r"求解器:  OR-Tools CP-SAT 9.x", size=14, color="#444")

fig.savefig("docs/single_machine_wct_model.png", dpi=200, facecolor="white", bbox_inches="tight")
print("PNG 已生成")
