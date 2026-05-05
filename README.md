# SDR-SOC-Estimator

**基于固相扩散慢弛豫修正的锂离子电池 SOC 高精度估计**

*High-Accuracy SOC Estimation for Lithium-Ion Batteries Based on Solid-Phase Diffusion Slow-Relaxation Compensation*

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 研究背景与动机

荷电状态（State of Charge, SOC）的精确估计是电池管理系统（BMS）最关键的功能之一，直接影响续航里程预测、充放电策略制定和电池安全保障。然而 SOC 无法直接测量，必须通过电压、电流、温度等可测信号间接估计，是该领域公认的研究难点。

SOC 估计方法可分为三类：

| 方法类别 | 代表方法 | 优点 | 缺点 |
|----------|----------|------|------|
| 安时积分法 | 库仑计数 | 简单直接，计算量极低 | 对初始误差和累积噪声敏感，长期漂移 |
| 数据驱动方法 | 神经网络、SVM | 无需物理模型，非线性拟合强 | 泛化能力有限，依赖大量高质量训练数据 |
| **基于模型 + 滤波** | KF/EKF/UKF | 精度与鲁棒性兼顾，闭环校正 | 模型结构决定估计精度上限 |

基于等效电路模型（ECM）结合卡尔曼滤波的闭环估计方法兼顾精度与鲁棒性，是工程应用的主流路线。一阶 RC（Thevenin）模型因参数少（仅 R<sub>0</sub>、R<sub>1</sub>、C<sub>1</sub> 三个参数）、实时性好，在车载 BMS 中应用最广。

然而，传统一阶 RC 模型存在一个**结构性缺陷**：用单一 RC 支路同时表征电化学极化（快动态，τ<sub>1</sub> ≈ 10~100 s）和固相扩散浓差极化（慢动态，τ<sub>sd</sub> ≈ 100~1000 s）。两者时间尺度相差 5~10 倍，单一时间常数 τ<sub>1</sub> 只能近似折中，无法解耦快慢动力学差异。在静置阶段，电压慢弛豫无法准确描述，导致 SOC 估计出现**系统性偏差**。

### 现有改进路线的局限

| 路线 | 方法 | 问题 |
|------|------|------|
| 增加 RC 阶数 | 二阶/三阶 ECM | 参数成倍增加、实时计算负担加重、过参数化风险 |
| 电化学模型 | P2D 模型、SPMe | 偏微分方程组、参数 > 30 个、毫秒级求解困难 |
| 分数阶模型 | 分数阶微积分 CPE | 分数阶算子存储历史状态、实时递推实现复杂 |

上述方案均难以同时满足嵌入式 BMS 的**实时性约束**（< 10 ms/步）和**参数可辨识性**要求。
## 本文贡献

在不增加 RC 支路、不改变模型阶数的前提下，提出一种**轻量化模型改进方案**：

1. **引入一阶惯性环节** G<sub>sd</sub>(s) = K<sub>sd</sub> / (τ<sub>sd</sub> · s + 1) 作为固相扩散修正项，仅增加 **2 个** 可辨识参数（τ<sub>sd</sub>、K<sub>sd</sub>），实现快慢动力学的**解耦表征**
2. **提出脉冲-静置两阶段参数离线辨识方法**：600s 脉冲充分激励慢弛豫动态，1800s 静置记录弛豫曲线，τ<sub>sd</sub> 和 K<sub>sd</sub> 辨识误差分别低至 **0.7%** 和 **0.2%**
3. **改进模型 SOC 估计 RMSE 从 1.23% 降至 0.60%**（降幅 **50.9%**），三项精度指标全部达标

| 指标 | 目标值 | 传统模型 | 改进模型 | 降幅 |
|------|:-----:|:-------:|:-------:|:----:|
| 最大误差 MaxE | ≤1.5% | 1.86% ✗ | **1.36% ✓** | 26.7% |
| 平均误差 MAE | ≤0.8% | 1.09% ✗ | **0.48% ✓** | 56.6% |
| 均方根误差 RMSE | ≤1.0% | 1.23% ✗ | **0.60% ✓** | 50.9% |

传统模型三项指标全部不达标，改进模型三项全部达标——仅增加了 1 个状态变量和 2 个参数，计算增量几乎为零。
## 方法论框架

整体框架分为三个层次：

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Physical System Layer  (物理系统层)                       ║
║                                                                              ║
║   ┌─────────────────┐          ┌─────────────────┐                          ║
║   │   Li-ion Battery │─────────▶│   Measurements  │                          ║
║   │  NMC / Graphite  │          │   V_t , I , T   │                          ║
║   └────────┬────────┘          └─────────────────┘                          ║
║            │                                                                 ║
║   ┌────────▼────────┐                                                        ║
║   │  OCV-SOC Char.  │   OCV(SOC) = 0.9·SOC³ − 1.5·SOC² + 1.8·SOC + 3.0    ║
║   └─────────────────┘                                                        ║
╚══════════════════════════════════════════════════════════╧═════════════════════╝
                                                           │
                                                           ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                       Model Layer  (模型层)                                  ║
║                                                                              ║
║   ┌─────────────────────────────┐    ┌──────────────────────────────────┐   ║
║   │ Offline Parameter ID        │    │ Improved Equivalent Circuit      │   ║
║   │ Pulse-Relaxation Method     │───▶│                                  │   ║
║   │ (600 s pulse + 1800 s rest) │    │ State: x = [SOC, V₁, V_sd]ᵀ     │   ║
║   │                             │    │ Output: Vₜ = OCV − V₁ − V_sd − I·R₀ │
║   │ → τ_sd , K_sd               │    │ New: G_sd(s) = K_sd/(τ_sd·s+1)  │   ║
║   └─────────────────────────────┘    └──────────────┬───────────────────┘   ║
╚═════════════════════════════════════════════════════╧═════════════════════════╝
                                                      │
                                                      ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                     Estimation Layer  (估计层)                               ║
║                                                                              ║
║   ┌──────────────────────────────────────────────────────────────────────┐  ║
║   │  Unscented Kalman Filter (UKF)                                        │  ║
║   │                                                                       │  ║
║   │  Sigma Points (2n+1) → State Prediction → Measurement Update          │  ║
║   │                                 ↓                                     │  ║
║   │                Kalman Gain → State Correction                         │  ║
║   │                                                                       │  ║
║   │  Process:  Q = diag(σ²_SOC, σ²_V₁, σ²_Vsd)                           │  ║
║   │  Measure:  R = σ²_v                                                   │  ║
║   └──────────────────────────────┬───────────────────────────────────────┘  ║
║                                  │                                          ║
║   ┌──────────────────────────────▼───────────────────────────────────────┐  ║
║   │  SOC Estimate with Error Bounds (±3σ)                               │  ║
║   └──────────────────────────────────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════════════╝
      │                                                           ▲
      └───────────────────────────────────────────────────────────┘
                      Voltage Innovation Feedback
```

### 第一层：物理系统层
Li-ion 电池（NMC/石墨体系）提供端电压 V<sub>t</sub>、电流 I、温度 T 测量信号。OCV-SOC 特性通过三阶多项式标定，覆盖电压范围 3.0~4.2 V。

### 第二层：模型层
- **改进等效电路模型**：在传统一阶 RC 基础上引入固相扩散修正项 V<sub>sd</sub>，状态向量由 n=2 扩展至 n=3
- **离线参数辨识**：脉冲-静置两阶段方法获取 τ<sub>sd</sub>、K<sub>sd</sub>——仅需常规充放电设备，无需 EIS 或 GITT。辨识结果 τ<sub>sd</sub> = 282.1 s（误差 0.7%），K<sub>sd</sub> = 0.0080（误差 0.2%）

### 第三层：估计层
UKF 执行 **Sigma 点生成 → 状态预测 → 观测预测 → 卡尔曼增益计算 → 状态校正** 五步递推。电压新息通过闭环反馈校正状态估计。无迹变换生成 2n+1 个确定性 Sigma 点直接传播状态分布，避免 EKF 的 Jacobian 线性化误差，对电池 OCV-SOC 强非线性系统的估计精度高 1~2 个数量级。
## 电池内部结构与固相扩散机理

![Battery Structure](fig_battery_structure.png)

锂离子电池由正极（NMC）、负极（石墨）、隔膜和电解液组成。放电时，Li⁺ 从负极石墨层间脱嵌，经电解液穿过隔膜嵌入正极 NMC 晶格，电子则通过外电路由负极流向正极，对外做功；充电过程反向。

### 固相扩散慢弛豫的物理本质

正负极活性材料均为微米级多孔颗粒（粒径 5~20 μm），Li⁺ 在颗粒内部的固相扩散系数 **D<sub>s</sub> ≈ 10⁻¹¹ ~ 10⁻¹³ cm²/s**，远小于液相扩散系数 **D<sub>e</sub> ≈ 10⁻⁵ ~ 10⁻⁶ cm²/s**——两者相差 **4~8 个数量级**，固相扩散是电池动力学的**限速步骤**。

弛豫时间量级估算（球形颗粒扩散模型）：

```
τ_sd ≈ R² / D_s

其中 R 为颗粒半径 (~5 μm)，D_s 为固相扩散系数 (~10⁻¹² cm²/s)
→ τ_sd ≈ (5×10⁻⁴ cm)² / 10⁻¹² cm²/s = 250 s
```

因此固相扩散弛豫时间 τ<sub>sd</sub> ≈ 100~1000 s，远超电化学极化时间常数 τ<sub>1</sub> ≈ 10~100 s。传统一阶 RC 模型将两者混入同一 RC 支路，τ<sub>1</sub> 只能近似折中两个时间尺度，无法解耦快慢动力学差异——这正是 **SOC 估计在静置阶段漂移的物理根源**。
## 改进等效电路模型

### 模型结构对比

**传统一阶 RC (Thevenin) 模型：**

```
  ┌──── R₁ ──── C₁ ────┐
  │                     │
  R₀                    │
  │                     │
  V_OCV(SOC)           V₁ (单 RC 同时表征快慢极化)
  │                     │
  └─────────────────────┘

Vₜ = OCV(SOC) − V₁ − I·R₀
x = [SOC, V₁]ᵀ  (n = 2)
```

**改进模型（本文提出）：**

```
  ┌──── R₁ ──── C₁ ────┐  ← 快极化: V₁ (τ₁ ≈ 37.5 s)
  │                     │
  R₀                    ├── V_sd (惯性环节, τ_sd ≈ 280 s)  ← 慢扩散
  │                     │
  V_OCV(SOC)            │
  │                     │
  └─────────────────────┘

Vₜ = OCV(SOC) − V₁ − V_sd − I·R₀
x = [SOC, V₁, V_sd]ᵀ  (n = 3)
```

### 状态空间方程

**状态方程（离散化，零阶保持器，采样周期 Δt = 0.1 s）：**

```
SOC(k+1)  = SOC(k) − Δt · I(k) / Qₙ
            └────── 安时积分 ──────┘

V₁(k+1)   = V₁(k) · exp(−Δt/τ₁) + I(k) · R₁ · (1 − exp(−Δt/τ₁))
            └──── 极化衰减 ────┘     └────── 电流激励响应 ──────┘

V_sd(k+1) = V_sd(k) · exp(−Δt/τ_sd) + I(k) · K_sd · (1 − exp(−Δt/τ_sd))
            └── 固相扩散慢弛豫衰减 ─┘   └────── 慢扩散响应 ──────┘
```

**观测方程：**

```
Vₜ = OCV(SOC) − V₁ − V_sd − I · R₀
```

### 物理量对照

| 术语 | 符号 | 物理意义 | 时间尺度 |
|------|:----:|----------|:--------:|
| 欧姆极化 | I·R₀ | 电子通过集流体/极耳 + Li⁺ 在电解液中迁移的欧姆电阻 | 瞬时（μs） |
| 电化学极化 | V₁ | 电荷转移反应（Butler-Volmer）+ SEI 膜扩散 | τ₁ ≈ 37.5 s（快） |
| **固相扩散** | **V<sub>sd</sub>** | **Li⁺ 在正负极活性材料颗粒内部的固相扩散** | **τ<sub>sd</sub> ≈ 280 s（慢）** |

### 核心创新

V₁ 表征电化学极化快动态，V<sub>sd</sub> 独立表征固相扩散慢弛豫——**两种动力学实现解耦**。仅增加 1 个状态变量和 2 个可辨识参数（τ<sub>sd</sub>、K<sub>sd</sub>），计算增量 < 3 次浮点运算/步，完整保留传统一阶 RC 模型实时性好的工程优势。
## UKF 状态估计算法

### 为什么选择 UKF？

扩展卡尔曼滤波（EKF）通过一阶 Taylor 展开线性化非线性系统，对电池 OCV-SOC 关系（三阶多项式，二阶导数非零）存在**固有线性化误差**。无迹卡尔曼滤波（UKF）通过无迹变换生成 2n+1 个确定性 Sigma 点，直接传播状态分布的均值和协方差，对任意非线性函数的估计精度可达 **Taylor 二阶展开精度**，无需计算 Jacobian 矩阵。

### 算法递推流程

```
初始化: x̂₀ = [SOC₀, 0, 0]ᵀ, P₀ = diag(0.01², 0.01², 0.005²)

对每个采样时刻 k = 0, 1, ..., N-1:

  (1) Sigma 点生成
      X⁽ⁱ⁾ = x̂ ± √((n+λ)·P)·eᵢ    (i = 0, ..., 2n)
      ↓

  (2) 状态预测（通过状态方程传播）
      X⁻⁽ⁱ⁾ = f(X⁽ⁱ⁾, Iₖ)           (i = 0, ..., 2n)
      x̂⁻ = Σᵢ Wₘ⁽ⁱ⁾ · X⁻⁽ⁱ⁾
      P⁻ = Q + Σᵢ W𝒸⁽ⁱ⁾ · (X⁻⁽ⁱ⁾ − x̂⁻)(X⁻⁽ⁱ⁾ − x̂⁻)ᵀ
      ↓

  (3) 观测预测（通过观测方程传播）
      ŷ⁽ⁱ⁾ = h(X⁻⁽ⁱ⁾)               (i = 0, ..., 2n)
      ŷ = Σᵢ Wₘ⁽ⁱ⁾ · ŷ⁽ⁱ⁾
      ↓

  (4) 卡尔曼增益计算
      Pᵧᵧ = R + Σᵢ W𝒸⁽ⁱ⁾ · (ŷ⁽ⁱ⁾ − ŷ)(ŷ⁽ⁱ⁾ − ŷ)ᵀ
      Pₓᵧ = Σᵢ W𝒸⁽ⁱ⁾ · (X⁻⁽ⁱ⁾ − x̂⁻)(ŷ⁽ⁱ⁾ − ŷ)ᵀ
      K = Pₓᵧ · Pᵧᵧ⁻¹
      ↓

  (5) 状态校正（新息驱动）
      x̂ = x̂⁻ + K · (Vₜ,ₘₑₐₛ − ŷ)
      P = P⁻ − K · Pᵧᵧ · Kᵀ
```

### UKF 参数配置

| 参数 | 数值 | 说明 |
|------|:----:|------|
| α | 1.0 | 分布扩展因子（控制 Sigma 点扩散范围） |
| β | 2.0 | 先验分布知识（高斯分布最优值） |
| κ | 0 | 次级缩放因子（n+κ=3 满足正定性） |
| Q (传统) | diag(1×10⁻⁸, 1×10⁻⁶) | 过程噪声协方差（n=2） |
| Q (改进) | diag(1×10⁻⁸, 1×10⁻⁶, 5×10⁻⁷) | 过程噪声协方差（n=3） |
| R | 4×10⁻⁶ | 测量噪声协方差（σ<sub>v</sub> = 2 mV，高斯白噪声） |
| Δt | 0.1 s | 采样周期（10 Hz） |

### Sigma 点权重

```
λ = α²·(n + κ) − n = 1²·(n + 0) − n = 0

Wₘ⁽⁰⁾ = λ / (n + λ) = 0        (均值权重中心点)
W𝒸⁽⁰⁾ = λ/(n+λ) + (1−α²+β) = 2  (协方差权重中心点)
Wₘ⁽ⁱ⁾ = W𝒸⁽ⁱ⁾ = 1/(2n)          (i = 1,...,2n，离轴点等权)
```

当 κ = 0, α = 1 时，λ = 0，中心点均值权重为 0——此时 UKF 退化为**中心差分滤波器**形式，对高斯过程仍保持二阶精度。
## OCV-SOC 特性曲线

![OCV-SOC](fig_ocv_soc.png)

NMC/石墨体系，开路电压范围 3.0~4.2 V，采用三阶多项式拟合：

```
OCV(SOC) = 0.9·SOC³ − 1.5·SOC² + 1.8·SOC + 3.0
```

三阶多项式在拟合精度的前提下避免了高阶 Runge 振荡，且在 UKF 状态传播中仅需 4 次乘加运算，计算友好。OCV-SOC 关系的**强非线性**（二阶导数 d²OCV/dSOC² ≠ 0）是选择 UKF 而非 EKF 的核心原因——EKF 对该非线性关系的线性化误差在 SOC 低端（< 20%）和高段（> 80%）尤为显著。
## 参数离线辨识

### 脉冲-静置两阶段方法

对新增参数 τ<sub>sd</sub> 和 K<sub>sd</sub>，提出仅需常规充放电设备的实用辨识方法。该方法充分利用 **固相扩散慢弛豫与电化学极化快动态的时间尺度分离**特性：

| 阶段 | 操作 | 持续 | 目的 |
|:----:|------|:----:|------|
| 脉冲 | 1C 恒流放电 | 600 s | 使 V<sub>sd</sub> 充分建立（稳态 ~17.7 mV）；Δt<sub>pulse</sub> ≫ τ<sub>1</sub> 确保 V₁ 已达稳态 |
| 静置 | 开路静置 | 1800 s | 记录端电压弛豫曲线；Δt<sub>rest</sub> ≫ τ<sub>sd</sub> 确保慢弛豫充分衰减 |

**关键设计考量**：600 s 脉冲时间选择——需要 > τ<sub>1</sub>（确保 V₁ 达稳态）且足够长以充分激励 V<sub>sd</sub>；1800 s 静置时间选择——需要 > 3τ<sub>sd</sub>（弛豫幅度衰减 95%）以覆盖完整的慢弛豫过程。

**阶段一**：利用已知 τ₁、R₁（由短脉冲辨识）扣除 V₁ 贡献：

```
V_corrected(t) = OCV − Vₜ(t) − V₁(t)
                = V_sd(t) + I·R₀
```

其中 `V₁(t) = V₁(0)·exp(−t/τ₁)`，V₁(0) 由脉冲结束时刻 RC 支路稳态值确定。

**阶段二**：对 V<sub>corrected</sub> 做单指数非线性最小二乘拟合（Levenberg-Marquardt 算法），目标函数：

```
min_{τ_sd, V_sd(0)} Σ || V_corrected(t) − V_sd(0)·exp(−t/τ_sd) − I·R₀ ||²
```

得到 τ<sub>sd</sub> 和 V<sub>sd</sub>(0)，反算增益：

```
K_sd = V_sd(0) / [I · (1 − exp(−t_pulse/τ_sd))]
```

### 辨识精度

![Parameter Identification](param_identification.png)

| 参数 | 真值 | 辨识值 | 绝对误差 | 相对误差 |
|------|:----:|:-----:|:--------:|:--------:|
| τ<sub>sd</sub> (s) | 280.0 | 282.1 | +2.1 s | **0.7%** |
| K<sub>sd</sub> | 0.0080 | 0.0080 | ~0 | **0.2%** |
| V<sub>sd,0</sub> (mV) | 17.65 | 17.58 | −0.07 mV | 0.4% |

辨识质量评定为 **GOOD**。精度来源：（1）600 s 长脉冲使 V<sub>sd</sub> 建立至稳态幅值的 88%，相较于传统短脉冲（10~30 s，仅激发 ~10%），信噪比提升 8 倍；（2）0.5 mV RMS 低噪声仿真环境；（3）两阶段策略先扣除快动态 V₁ 再辨识慢动态 τ<sub>sd</sub>——避免了快慢动力学之间的相互污染，对测量噪声的鲁棒性优于传统对数-线性回归法。
## 仿真结果

### 实验工况

```
工况一：1C 放电 1500 s → 静置 900 s → 1C 充电 1500 s → 静置 900 s
         └─ 快响应 ─┘    └─ 慢弛豫 ─┘    └─ 快响应 ─┘    └─ 慢弛豫 ─┘

总时长：4800 s (80 min)
采样周期：0.1 s (共 48,000 步)
测量噪声：σ_v = 2 mV (高斯白噪声，加在端电压上)
电流测量：使用真值（排除电流噪声干扰，隔离模型误差）
```

工况设计包含两个完整的放电-静置和充电-静置循环，覆盖：
- **快响应阶段**（充放电）：V₁ + V<sub>sd</sub> + I·R₀ 三者叠加，检验 UKF 在多分量耦合下的估计能力
- **慢弛豫阶段**（静置）：仅有 V₁ 和 V<sub>sd</sub> 衰减，I·R₀ = 0，**检验慢弛豫表征的核心场景**

三组对比模型：
1. **传统一阶 RC + UKF**（n=2，基线）——无 V<sub>sd</sub> 修正
2. **改进模型 + UKF**（n=3）——本文方法，τ<sub>sd</sub> 离线固定
3. **自适应模型 + UKF**（n=4）——τ<sub>sd</sub> 在线估计，初值 300 s（误差 +7.1%）

### 三模型 SOC 估计综合对比

![Three-way Comparison](three_way_comparison.png)

改进模型（蓝色虚线）全程紧密跟踪真实 SOC（黑色实线）；传统模型（红色）在静置阶段出现**系统性漂移**（~1.5%~2%），且漂移方向随工况切换而改变——放电后静置偏小、充电后静置偏大，表明传统模型将慢弛豫电压残差错误映射为 SOC 修正。

### SOC 估计误差分布

![Error Distribution](fig_error_distribution.png)

改进模型误差**集中在 ±0.5% 以内**，均值更接近零、方差更小；传统模型分散至 ±2%，呈现明显的**双峰分布**——分别对应放电后静置和充电后静置两个慢弛豫阶段。误差分布形态直接反映了 V<sub>sd</sub> 修正的有效性：改进模型消除了慢弛豫引起的系统性误差源。

### 端电压分量分解

![Voltage Decomposition](fig_voltage_decomposition.png)

三组模型的端电压估计 RMSE 均处于较低水平（0.98~1.15 mV），表明 UKF 能有效融合电压测量新息，在端电压层面三个模型表现接近。

然而，**相近的端电压精度并不等同 SOC 精度**：
- 传统模型：SOC RMSE = 1.23%，V<sub>t</sub> RMSE = 0.98 mV
- 改进模型：SOC RMSE = 0.60%，V<sub>t</sub> RMSE = 1.15 mV

**V<sub>t</sub> RMSE 与 SOC RMSE 出现负相关**——改进模型端电压误差略大（+0.17 mV），但 SOC 精度提升近一倍。根本原因：传统模型缺少 V<sub>sd</sub> 修正项，UKF 将静置阶段固相扩散引起的电压弛豫 **错误映射为 SOC 修正**（可观性问题）；改进模型正确分配了电压残差的物理来源——V₁ 管快动态、V<sub>sd</sub> 管慢动态——UKF 不再"张冠李戴"地修正 SOC。

### 静置阶段 SOC 漂移抑制

![Rest Period Detail](rest_period_detail.png)

放电结束后 900 s 静置期间，端电压从 ~3.5 V 弛豫回升至 ~3.65 V（ΔV ≈ 150 mV）。各极化分量贡献：

| 分量 | 幅值 | 时间常数 | 衰减特征 |
|------|:----:|:--------:|----------|
| I·R₀ | ~62.5 mV | 瞬时 | 电流切断即刻消失 |
| V₁ | ~37.5 mV | τ₁ = 37.5 s | 60 s 内衰减 80% |
| **V<sub>sd</sub>** | **~20 mV** | **τ<sub>sd</sub> = 280 s** | **900 s 仅衰减 96%** |

V<sub>sd</sub> 幅值虽最小（~20 mV），但因 τ<sub>sd</sub>（280 s）远超 τ₁（37.5 s），在静置阶段**累积效应显著**——这就是"慢弛豫"的物理本质：幅值不大，但持续时间极长。

| 模型 | 静置阶段 SOC 偏差 | 漂移方向 |
|------|:---------------:|:--------:|
| 传统模型 | 1.5% ~ 2%（漂移） | 放电后偏小，充电后偏大 |
| **改进模型** | **< 0.3%** | 无系统性漂移 |

### 自适应 UKF 性能

自适应模型（n=4，τ<sub>sd</sub> 在线估计）实现了平均误差 0.55% 和 RMSE 0.73%（均达标），τ<sub>sd</sub> 在线收敛至 293.1 s（与真值 280 s 偏差 4.7%），验证了增广状态 UKF 框架的可行性。

但最大误差 1.86% 与传统模型持平（未达 ≤1.5% 目标），表明联合状态-参数估计增加了滤波器自由度与不确定性：**4 维状态空间中存在 SOC 与 τ<sub>sd</sub> 的弱可辨识性耦合**——两者都通过影响端电压来驱动新息，在静置阶段尤为难以区分。暂态稳定性不及固定参数方案（n=3）。
## 仿真参数

| 参数 | 符号 | 数值 | 单位 | 物理含义 |
|------|:----:|:----:|:----:|----------|
| 额定容量 | Q<sub>n</sub> | 2.5 | Ah | 18650 电芯典型值 |
| 欧姆内阻 | R₀ | 0.025 | Ω | 脉冲开始/结束瞬态压降 |
| 极化电阻 | R₁ | 0.015 | Ω | 电化学极化稳态幅值 |
| 极化电容 | C₁ | 2500 | F | τ₁ = R₁C₁ = 37.5 s |
| RC 时间常数 | τ₁ = R₁C₁ | 37.5 | s | 电化学极化时间尺度 |
| 固相扩散时间常数 | τ<sub>sd</sub> | 280 | s | 颗粒内部 Li⁺ 扩散弛豫 |
| 固相扩散增益 | K<sub>sd</sub> | 0.008 | — | V<sub>sd</sub> 对电流的响应强度 |
| 采样周期 | Δt | 0.1 | s | 满足 τ₁/Δt = 375 ≫ 1 |
| 测量噪声标准差 | σ<sub>v</sub> | 2.0 | mV | 典型 BMS 电压采样噪声 |
## 讨论与局限

1. **仅基于仿真验证**：Python 平台搭建，"真实电池"由改进模型模拟（噪声环境下的自洽验证），需实物电池实验确认。仿真自洽验证的局限性：改进模型对自身生成的数据有结构性优势
2. **OCV-SOC 采用固定多项式**：未考虑温度和老化影响。实际电池 OCV 随温度（−20~60°C）偏移 5~20 mV，随循环老化（> 500 次）偏移 10~30 mV
3. **未在动态驾驶工况下验证**：需在 UDDS、FUDS、US06 等瞬态工况下进一步检验模型泛化能力——动态工况下 SOC 持续变化，无长静置期，V<sub>sd</sub> 的累积效应模式与本文工况不同
4. **单温度点辨识**：参数在室温（25°C）辨识，低温下 τ<sub>sd</sub> 可能增大 2~5 倍（Arrhenius 关系），需温度补偿
5. **仅考虑恒流脉冲**：实际充电为 CC-CV 模式，CV 阶段电流递减对 V<sub>sd</sub> 的激励与恒流脉冲不同

### 未来工作

- **实物电池实验验证**：在 18650/21700 电芯上进行脉冲-静置辨识和 UKF 在线估计
- **温度/老化补偿**：建立 τ<sub>sd</sub> = f(T, SOH) 映射关系，实现全寿命周期自适应
- **SOC-SOH 联合估计**：利用 τ<sub>sd</sub> 随老化增长的趋势（D<sub>s</sub> 下降 → τ<sub>sd</sub> 上升）作为 SOH 指示器
- **动态工况泛化**：在 UDDS/FUDS 工况下与二阶 RC、分数阶模型对比
- **硬件在环验证**：在 BMS 嵌入式平台（STM32/TC387）上评估实时性
## 参考文献

1. Plett G L. Extended Kalman filtering for battery management systems of LiPB-based HEV battery packs — Part 2: Modeling and identification[J]. Journal of Power Sources, 2004, 134(2): 262-276.
2. Plett G L. Extended Kalman filtering for battery management systems of LiPB-based HEV battery packs — Part 3: State and parameter estimation[J]. Journal of Power Sources, 2004, 134(2): 277-292.
3. Julier S J, Uhlmann J K. Unscented filtering and nonlinear estimation[J]. Proceedings of the IEEE, 2004, 92(3): 401-422.
4. Hu X, Li S, Peng H. A comparative study of equivalent circuit models for Li-ion batteries[J]. Journal of Power Sources, 2012, 198: 359-367.
5. He H, Xiong R, Guo H, et al. Comparison study on the battery models used for the energy management of batteries in electric vehicles[J]. Energy Conversion and Management, 2012, 64: 113-121.
6. Chen M, Rincon-Mora G A. Accurate electrical battery model capable of predicting runtime and I-V performance[J]. IEEE Transactions on Energy Conversion, 2006, 21(2): 504-511.
7. Waag W, Fleischer C, Sauer D U. Critical review of the methods for monitoring of lithium-ion batteries in electric and hybrid vehicles[J]. Journal of Power Sources, 2014, 258: 321-339.
8. Xiong R, Cao J, Yu Q, et al. Critical review on the battery state of charge estimation methods for electric vehicles[J]. IEEE Access, 2018, 6: 1832-1843.
9. Zhang C, Allafi W, Dinh Q, et al. Online estimation of battery equivalent circuit model parameters and state of charge using decoupled least squares technique[J]. Energy, 2018, 142: 678-688.
10. Doyle M, Fuller T F, Newman J. Modeling of galvanostatic charge and discharge of the lithium/polymer/insertion cell[J]. Journal of the Electrochemical Society, 1993, 140(6): 1526-1533.
11. Santhanagopalan S, Guo Q, Ramadass P, et al. Review of models for predicting the cycling performance of lithium ion batteries[J]. Journal of Power Sources, 2006, 156(2): 620-628.
12. Wang Y, Liu C, Pan R, et al. Modeling and state-of-charge prediction of lithium-ion battery and ultracapacitor hybrids with a co-estimator[J]. Energy, 2017, 121: 739-750.
13. Xu J, Mi C C, Cao B, et al. The state of charge estimation of lithium-ion batteries based on a proportional-integral observer[J]. IEEE Transactions on Vehicular Technology, 2014, 63(4): 1614-1621.
14. Xiong R, Sun F, Chen Z, et al. A data-driven multi-scale extended Kalman filtering based parameter and state estimation approach of lithium-ion polymer battery in electric vehicles[J]. Applied Energy, 2014, 113: 463-476.
15. Li J, Lai Q, Wang L, et al. A method for SOC estimation based on simplified mechanistic model for LiFePO₄ battery[J]. Energy, 2016, 114: 1266-1276.
16. Dey S, Ayalew B, Pisu P. Nonlinear robust observers for state-of-charge estimation of lithium-ion cells based on a reduced electrochemical model[J]. IEEE Transactions on Control Systems Technology, 2015, 23(5): 1935-1942.
17. Wei Z, Meng S, Xiong B, et al. Enhanced online model identification and state of charge estimation for lithium-ion battery with a FBCRLS based observer[J]. Applied Energy, 2016, 181: 332-341.
18. Zou Y, Hu X, Ma H, et al. Combined state of charge and state of health estimation over lithium-ion battery cell cycle lifespan for electric vehicles[J]. Journal of Power Sources, 2015, 273: 793-803.
19. 熊瑞. 动力电池管理系统核心算法[M]. 北京: 机械工业出版社, 2018.
20. 何洪文, 熊瑞, 孙逢春. 锂离子动力电池荷电状态估计方法综述[J]. 机械工程学报, 2011, 47(22): 76-83.
21. 戴海峰, 孙泽昌, 魏学哲. 锂离子电池电化学阻抗谱研究综述[J]. 电源技术, 2014, 38(9): 1749-1752.
22. 张彩萍, 姜久春, 张维戈, 等. 锂离子电池等效电路模型参数辨识方法研究[J]. 电源技术, 2015, 39(1): 55-58.
23. 庞辉, 杨世春, 邓忠伟. 基于分数阶模型的锂离子电池建模与荷电状态估计[J]. 中国科学: 技术科学, 2016, 46(12): 1297-1306.
24. 胡晓松, 李升波, 彭晖. 车用锂离子动力电池模型对比研究[J]. 汽车工程, 2012, 34(9): 779-784.
25. 王震坡, 孙逢春, 张承宁. 电动汽车动力电池组建模方法研究[J]. 机械工程学报, 2008, 44(10): 104-108.
26. 卢兰光, 李建秋, 华剑锋, 等. 基于PNGV模型的锂离子电池SOC估计方法[J]. 清华大学学报(自然科学版), 2011, 51(5): 699-703.
27. 刘大同, 周建宝, 郭力萌, 等. 锂离子电池健康评估和寿命预测综述[J]. 仪器仪表学报, 2015, 36(1): 1-16.
28. 李哲, 卢兰光, 欧阳明高. 提高安时积分法估算电池SOC精度的方法比较[J]. 清华大学学报(自然科学版), 2010, 50(8): 1293-1296.
29. 彭振翔. 电动汽车动力电池建模及SOC估算研究[D]. 成都: 西南交通大学, 2018.
30. 侯宇欣, 彭振翔. 基于固相扩散慢弛豫修正的锂离子电池 SOC 高精度估计方法研究[J]. 电工技术学报, 2025. (在审)
## 项目结构

```
battery_soc/
├── main.py                        # 主仿真入口（三模型 UKF 对比）
│   ├── run_simulation()            #   - 生成工况 → 真实电池模拟 → UKF 估计
│   └── plot_results()             #   - 6-panel + 2-panel 论文图表
├── ukf.py                         # UKF 估计器核心
│   └── UKFEstimator(model_type)   #   支持 n=2(traditional)/3(improved)/4(adaptive)
│       ├── _sigma_points()        #     Cholesky 分解生成 2n+1 Sigma 点
│       ├── _f()                   #     状态转移方程（离散化）
│       ├── _h()                   #     观测方程
│       ├── predict()              #     Sigma 点传播 + 预测均值/协方差
│       └── update()               #     新息计算 + 卡尔曼增益 + 状态校正
├── parameters.py                  # 电池参数 & 工况定义
│   ├── Q_n, R0, R1, C1, tau1     #   一阶 RC 模型参数
│   ├── tau_sd, K_sd              #   固相扩散修正参数
│   ├── ocv_soc_poly(SOC)         #   OCV-SOC 三阶多项式
│   ├── generate_current_profile() #   工况电流序列生成
│   └── dt, SOC_init              #   仿真参数
├── param_identify.py              # 脉冲-静置两阶段参数辨识
│   ├── simulate_pulse_rest()      #    600 s 脉冲 + 1800 s 静置仿真
│   ├── stage1_remove_V1()         #    阶段一：扣除 V₁ 快极化贡献
│   └── stage2_fit_Vsd()          #    阶段二：指数拟合得 τ_sd, K_sd
├── run_p0.py                      # P0 精度验证（N=1000 Monte Carlo）
├── generate_paper.py              # Word 论文生成（python-docx + OMML 原生公式）
├── generate_methodology_fig.py    # 方法论框架流程图
├── generate_extra_figures.py      # 辅助图表（误差分布、电压分解）
├── render_drawio.py               # Draw.io XML → PNG 渲染
├── fig_methodology.drawio.xml     # 方法论框架图源文件（Draw.io 可编辑）
├── fig_methodology.png            # 图 1  方法论框架
├── fig_battery_structure.png      # 图 2  电池内部结构示意图
├── fig_ocv_soc.png                # 图 3  OCV-SOC 特性曲线
├── three_way_comparison.png       # 图 4  三模型 SOC/电压/V_sd 综合对比
├── fig_error_distribution.png     # 图 5  SOC 估计误差分布直方图
├── fig_voltage_decomposition.png  # 图 6  端电压极化分量分解
├── rest_period_detail.png         # 图 7  静置阶段 SOC 漂移局部放大
├── param_identification.png       # 图 8  参数辨识可视化（脉冲+弛豫+拟合残差）
└── literature/                    # 参考文献（GB/T 7714 格式）
```
## 快速开始

### 环境要求

- Python 3.8+
- 依赖包：

```bash
pip install numpy matplotlib scipy python-docx lxml
```

### 运行仿真

```bash
# 核心仿真：三模型 SOC 对比（传统 vs 改进 vs 自适应）
python main.py

# 参数离线辨识：脉冲-静置两阶段方法
python param_identify.py

# 精度验证：P0 指标 Monte Carlo 统计
python run_p0.py
```

### 运行输出

`main.py` 输出：
- 终端：三模型 SOC 误差对比表 + 达标判定 + 改进幅度统计
- `comparison_results.png`：6-panel 综合对比图（电流、端电压、SOC估计、SOC误差、V_sd、误差柱状图）
- `rest_period_detail.png`：静置阶段局部放大图（SOC + 端电压弛豫）
- `three_way_comparison.png`：三模型对比大图（用于论文）

`param_identify.py` 输出：
- 终端：τ<sub>sd</sub>、K<sub>sd</sub> 辨识值、误差、拟合质量评定
- `param_identification.png`：脉冲-静置两阶段可视化

### 切换模型类型

在 `main.py` 中修改 UKF 初始化参数：

```python
# 传统模型 (n=2)
ukf = UKFEstimator(model_type='traditional', Q=Q_trad, R=R_ukf)

# 改进模型 (n=3) — 本文方法
ukf = UKFEstimator(model_type='improved', Q=Q_impr, R=R_ukf)

# 自适应模型 (n=4) — τ_sd 在线估计
ukf = UKFEstimator(model_type='adaptive', Q=Q_adaptive, R=R_ukf)
```

### 自定义参数

编辑 `parameters.py` 修改电池参数、OCV-SOC 曲线或工况电流：

```python
# 修改额定容量
Q_n = 3.0  # Ah

# 修改固相扩散参数
tau_sd = 350  # s (低温下增大)
K_sd = 0.012

# 自定义工况电流序列
def generate_current_profile(dt):
    # 返回 numpy 数组
    ...
```
## 作者

**彭振翔** — 西南交通大学 环境工程学院
## 许可证

MIT License

Copyright (c) 2025 彭振翔
