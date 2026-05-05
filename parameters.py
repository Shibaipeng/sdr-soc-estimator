"""
锂离子电池参数配置、OCV-SOC曲线、工况电流定义
论文核心：提升一阶RC模型SOC估算精度、兼顾工程实用性
"""

import numpy as np

# ==================== 电池基本参数 ====================
Q_n_Ah = 2.5          # 电池额定容量 (Ah)
Q_n = Q_n_Ah * 3600   # 换算为库仑 (As)
R0 = 0.025             # 欧姆内阻 (Ω)

# --- 传统一阶RC模型参数 (Thevenin) ---
R1 = 0.015             # 极化电阻 (Ω)
C1 = 2500.0            # 极化电容 (F)
tau1 = R1 * C1         # RC时间常数 (s) ≈ 37.5s — 表征电化学极化(快)

# --- 改进模型：固相扩散修正项参数 ---
tau_sd = 280.0         # 固相扩散时间常数 (s) — 表征慢弛豫
K_sd   = 0.008         # 固相扩散增益系数

# ==================== 仿真参数 ====================
dt = 0.1               # 采样周期 (s), 10Hz
SOC_init = 0.80        # 初始SOC (始于80%)

# ==================== 工况电流序列 ====================
def generate_current_profile(dt=0.1):
    """
    生成贴合车载实际的工况电流序列：
    恒流放电(1C) → 静置 → 恒流充电(1C) → 静置
    """
    I_1C = Q_n_Ah        # 1C倍率电流 = 2.5A
    t_discharge = 1500   # 放电1500s
    t_rest1     = 900    # 静置900s (15min, 展示慢弛豫)
    t_charge    = 1500   # 充电1500s
    t_rest2     = 900    # 静置900s

    # 构建各段的电流与时间 (正电流=放电, 负电流=充电)
    segments = [
        (I_1C,  t_discharge),   # 放电 (I>0 → SOC下降)
        (0.0,   t_rest1),       # 静置
        (-I_1C, t_charge),      # 充电 (I<0 → SOC上升)
        (0.0,   t_rest2),       # 静置
    ]

    I_list = []
    for I_val, duration in segments:
        n_steps = int(duration / dt)
        I_list.extend([I_val] * n_steps)

    return np.array(I_list)


# ==================== OCV-SOC 关系曲线 ====================
def ocv_soc_poly(SOC):
    """
    OCV-SOC多项式关系 (NMC/石墨体系典型曲线)
    SOC in [0, 1], OCV in [3.0V, 4.2V], dOCV/dSOC ≈ 0.8~1.8 V
    """
    # 系数: 3.0 + 1.8*SOC - 1.5*SOC^2 + 0.9*SOC^3
    p = np.array([0.9, -1.5, 1.8, 3.0])
    return np.polyval(p, SOC)


def d_ocv_d_soc(SOC):
    """OCV对SOC的导数"""
    p = np.array([0.9, -1.5, 1.8, 3.0])
    dp = np.polyder(p)
    return np.polyval(dp, SOC)
