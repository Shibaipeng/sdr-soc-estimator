"""
P0-2: 固相扩散参数离线辨识方法
=================================
利用单次长脉冲-静置实验 + 指数拟合，离线提取 tau_sd 和 K_sd。

原理:
  静置阶段 (I=0): Vt = OCV(SOC) - V1*exp(-t/tau1) - V_sd*exp(-t/tau_sd)
  tau1 ≈ 37.5s, tau_sd ≈ 280s
  当 t >> 5*tau1 (t > 200s):  V1 已归零 → Vt ≈ OCV - V_sd*exp(-t/tau_sd)
  → ln(OCV - Vt) ≈ ln(V_sd0) - t/tau_sd  (线性拟合)

步骤:
  1. 在已知 SOC 下施加长脉冲电流 (足够长以建立显著 V_sd)
  2. 长时间静置, 记录端电压
  3. 对静置尾部 (t > 5*tau1) 做线性拟合 → tau_sd, V_sd0
  4. 由 V_sd0 反算 K_sd
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

from parameters import (
    Q_n, R0, R1, C1, tau1, tau_sd as TRUE_TAU_SD,
    K_sd as TRUE_K_SD, dt, ocv_soc_poly
)


def simulate_pulse_rest(SOC_start, I_pulse, t_pulse, t_rest, sigma_v=0.001):
    """
    模拟脉冲-静置实验的真值响应

    Returns
    -------
    t, I, Vt_true, Vt_meas : 时间/电流/电压序列
    SOC_end : 脉冲结束时的 SOC
    V_sd0_true : 静置初始 V_sd 真值
    idx_rest_start : 静置阶段起始索引
    """
    t_pre = 600
    n_pre = int(t_pre / dt)
    n_pulse = int(t_pulse / dt)
    n_rest = int(t_rest / dt)
    n_total = n_pre + n_pulse + n_rest

    t = np.arange(n_total) * dt
    I = np.zeros(n_total)
    Vt_true = np.zeros(n_total)

    SOC = SOC_start
    V1, V_sd = 0.0, 0.0

    for k in range(n_total):
        Ik = I_pulse if k < n_pre + n_pulse else 0.0
        # 预静置阶段电流也为 0
        if k < n_pre:
            Ik = 0.0
        elif k < n_pre + n_pulse:
            Ik = I_pulse
        else:
            Ik = 0.0

        I[k] = Ik
        Vt_true[k] = ocv_soc_poly(SOC) - V1 - V_sd - Ik * R0

        SOC -= dt * Ik / Q_n
        V1 = V1 * np.exp(-dt / tau1) + Ik * R1 * (1 - np.exp(-dt / tau1))
        V_sd = V_sd * np.exp(-dt / TRUE_TAU_SD) + Ik * TRUE_K_SD * (1 - np.exp(-dt / TRUE_TAU_SD))

    # 静置初始 V_sd (脉冲最后一步累积的值)
    V_sd_temp = 0.0
    for _ in range(n_pulse):
        V_sd_temp = V_sd_temp * np.exp(-dt / TRUE_TAU_SD) \
                    + I_pulse * TRUE_K_SD * (1 - np.exp(-dt / TRUE_TAU_SD))
    V_sd0_true = V_sd_temp

    SOC_end = SOC  # 静置阶段 SOC 不变

    np.random.seed(123)
    Vt_meas = Vt_true + np.random.randn(n_total) * sigma_v

    idx_rest_start = n_pre + n_pulse
    return t, I, Vt_true, Vt_meas, SOC_end, V_sd0_true, idx_rest_start


def identify_params(t, Vt_meas, SOC_end, I_pulse, t_pulse,
                    idx_rest_start):
    """
    两阶段法辨识 tau_sd 和 K_sd

    阶段1: 利用已知 τ1, R1 计算 V1(0) = I*R1*(1 - e^(-t_pulse/τ1))
           从端电压中扣除 V1 的贡献
    阶段2: 对残差 V_corrected = OCV - Vt - V1(t) 做单指数拟合
           V_corrected ≈ V_sd(0)*exp(-t/τ_sd)
           → ln(V_corrected) ≈ ln(V_sd0) - t/τ_sd (线性回归)
    """
    t_rest = t[idx_rest_start:] - t[idx_rest_start]
    Vt_rest = Vt_meas[idx_rest_start:]
    ocv = ocv_soc_poly(SOC_end)

    # 阶段1: 扣除已知 V1 贡献
    V1_0 = I_pulse * R1 * (1 - np.exp(-t_pulse / tau1))
    V1_contrib = V1_0 * np.exp(-t_rest / tau1)
    V_corrected = ocv - Vt_rest - V1_contrib

    # 阶段2: 非线性最小二乘拟合 V_corrected = V_sd0 * exp(-t / tau_sd)
    from scipy.optimize import curve_fit

    def exp_decay(t, V0, tau):
        return V0 * np.exp(-t / tau)

    idx_use = t_rest >= 5.0  # 跳过最开始的瞬态
    t_use = t_rest[idx_use]
    V_use = np.maximum(V_corrected[idx_use], 1e-8)

    try:
        popt, _ = curve_fit(exp_decay, t_use, V_use,
                            p0=[V_use[0], 300.0],
                            bounds=([1e-6, 50.0], [0.5, 2000.0]),
                            maxfev=5000)
        V_sd0_est, tau_sd_est = popt[0], popt[1]
    except Exception:
        # fallback to log-linear
        y = np.log(V_use)
        A = np.column_stack([np.ones_like(t_use), t_use])
        coeff, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
        V_sd0_est = np.exp(coeff[0])
        tau_sd_est = -1.0 / coeff[1] if coeff[1] < -1e-6 else 999.0

    # 反算 K_sd
    if abs(I_pulse) > 0.01:
        K_sd_est = V_sd0_est / (I_pulse * (1 - np.exp(-t_pulse / tau_sd_est)))
    else:
        K_sd_est = 0.0

    return tau_sd_est, K_sd_est, V_sd0_est, t_rest, ocv, V_corrected


def run_identification():
    """运行参数辨识实验并评估精度"""
    print("=" * 65)
    print("  P0-2: Parameter Identification (Pulse-Relaxation)")
    print("=" * 65)

    # 实验参数 — 长脉冲确保 V_sd 充分建立
    SOC_start = 0.80
    I_pulse = 2.5       # 1C 放电 (A)
    t_pulse = 600.0     # 脉冲 10min → V_sd 达到稳态的 88%
    t_rest  = 1800.0    # 静置 30min → 充分弛豫
    sigma_v = 0.0005    # 0.5mV RMS (实验室DAQ水平)

    V_sd_ss = abs(I_pulse) * TRUE_K_SD  # 稳态值
    V_sd_exp = V_sd_ss * (1 - np.exp(-t_pulse / TRUE_TAU_SD))

    print(f"\n[Experiment Setup]")
    print(f"  Initial SOC: {SOC_start*100:.0f}%")
    print(f"  Pulse: {I_pulse:.1f}A (1C) for {t_pulse:.0f}s")
    print(f"  V_sd steady-state: {V_sd_ss*1000:.1f}mV")
    print(f"  V_sd after pulse:  {V_sd_exp*1000:.1f}mV (expected)")
    print(f"  Rest: {t_rest:.0f}s ({t_rest/60:.0f}min)")
    print(f"  Voltage noise: {sigma_v*1000:.1f}mV RMS")

    # 模拟
    t, I, Vt_true, Vt_meas, SOC_end, V_sd0_true, idx_rest_start = \
        simulate_pulse_rest(SOC_start, I_pulse, t_pulse, t_rest, sigma_v=sigma_v)

    # 辨识
    tau_sd_est, K_sd_est, V_sd0_est, t_rest, ocv, V_corrected = \
        identify_params(t, Vt_meas, SOC_end, I_pulse, t_pulse, idx_rest_start)

    # 误差
    err_tau = abs(tau_sd_est - TRUE_TAU_SD) / TRUE_TAU_SD * 100
    err_K   = abs(K_sd_est - TRUE_K_SD) / TRUE_K_SD * 100

    print(f"\n[Identification Results]")
    print(f"{'Parameter':<16}{'True':>12}{'Identified':>12}{'Error':>12}")
    print(f"{'-'*52}")
    print(f"{'tau_sd (s)':<16}{TRUE_TAU_SD:>12.1f}{tau_sd_est:>12.1f}{err_tau:>11.1f}%")
    print(f"{'K_sd':<16}{TRUE_K_SD:>12.4f}{K_sd_est:>12.4f}{err_K:>11.1f}%")
    print(f"{'V_sd0 (mV)':<16}{V_sd0_true*1000:>12.2f}{V_sd0_est*1000:>12.2f}")
    print(f"{'-'*52}")

    quality = "GOOD" if (err_tau < 15 and err_K < 15) else \
              "ACCEPTABLE" if (err_tau < 25 and err_K < 25) else "POOR"
    print(f"  Quality: {quality}")

    # 可视化
    plot_identification(t, I, Vt_true, Vt_meas, t_rest, V_corrected, ocv,
                        idx_rest_start, tau_sd_est, V_sd0_est,
                        TRUE_TAU_SD, V_sd0_true, K_sd_est)

    return tau_sd_est, K_sd_est, err_tau, err_K


def plot_identification(t, I, Vt_true, Vt_meas, t_rest, V_corrected, ocv,
                        idx_rest_start, tau_sd_est, V_sd0_est,
                        tau_sd_true, V_sd0_true, K_sd_est):
    """可视化辨识过程"""
    for font_name in ['SimHei', 'Microsoft YaHei', 'Noto Sans CJK SC', 'DejaVu Sans']:
        try:
            matplotlib.font_manager.findfont(font_name, fallback_to_default=False)
            plt.rcParams['font.sans-serif'] = [font_name]
            break
        except Exception:
            continue

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle('Parameter Identification: Pulse-Relaxation Method',
                 fontsize=13, fontweight='bold')

    t_min = t / 60
    t_rest_rel = t[idx_rest_start:] - t[idx_rest_start]
    Vt_true_rest = Vt_true[idx_rest_start:]
    Vt_meas_rest = Vt_meas[idx_rest_start:]

    # (a) Current
    ax = axes[0, 0]
    ax.plot(t_min, I, 'b-', linewidth=1.0)
    ax.fill_between(t_min, I, 0, alpha=0.08, color='blue')
    ax.set_ylabel('Current (A)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(a) Pulse Current Profile')
    ax.grid(True, alpha=0.3)

    # (b) Terminal voltage
    ax = axes[0, 1]
    ax.plot(t_min, Vt_true, 'k-', linewidth=0.8, alpha=0.6, label='True Vt')
    ax.plot(t_min, Vt_meas, 'gray', linewidth=0.3, alpha=0.5, label='Measured')
    ax.axvline(x=t[idx_rest_start] / 60, color='red', linestyle='--',
               linewidth=0.8, label='Rest begins')
    ax.set_ylabel('Terminal Voltage (V)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(b) Terminal Voltage Response')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (c) 两阶段法: 扣除 V1 后做 V_sd 指数拟合
    ax = axes[1, 0]
    # V_corrected = OCV - Vt - V1_contrib ≈ V_sd(t)
    V_corr_true = np.maximum(ocv - Vt_true_rest
                             - V_sd0_true * 0 * np.exp(-t_rest_rel / tau1), 1e-6)
    # 简化: 直接用 V_corrected (already computed in identify_params)
    ax.plot(t_rest_rel, V_corrected * 1000, '.', markersize=1.0,
            color='gray', alpha=0.5, label='V_corrected (meas)')

    # 真实 V_sd 衰减
    V_sd_true_decay = V_sd0_true * np.exp(-t_rest_rel / tau_sd_true) * 1000
    ax.plot(t_rest_rel, V_sd_true_decay, 'k-', linewidth=1.2, label='True V_sd(t)')

    # 拟合曲线
    V_sd_fit = V_sd0_est * np.exp(-t_rest_rel / tau_sd_est) * 1000
    ax.plot(t_rest_rel, V_sd_fit, 'r--', linewidth=1.5,
            label=f'Fit: tau={tau_sd_est:.0f}s')

    ax.set_ylabel('V_sd (mV)')
    ax.set_xlabel('Rest Time (s)')
    ax.set_title('(c) Two-Stage Fit: V1 Subtracted, V_sd Fitted')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (d) Parameter accuracy
    ax = axes[1, 1]
    params = ['tau_sd (s)', 'K_sd']
    true_vals = [tau_sd_true, TRUE_K_SD]
    est_vals = [tau_sd_est, K_sd_est]
    x = np.arange(len(params))
    width = 0.3
    bars1 = ax.bar(x - width/2, true_vals, width, label='True',
                   color='#2c3e50')
    bars2 = ax.bar(x + width/2, est_vals, width, label='Identified',
                   color='#e74c3c')
    ax.set_xticks(x)
    ax.set_xticklabels(params)
    ax.set_title('(d) Parameter Identification Accuracy')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2, axis='y')
    for bar, val in zip(bars1, true_vals):
        ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
                f'{val:.3g}', ha='center', va='bottom', fontsize=9)
    for bar, val in zip(bars2, est_vals):
        ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
                f'{val:.3g}', ha='center', va='bottom', fontsize=9, color='#c0392b')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = os.path.join(os.path.dirname(__file__), 'param_identification.png')
    fig.savefig(out_path, dpi=200, bbox_inches='tight')
    print(f"\n  Figure saved: {out_path}")
    plt.close(fig)


if __name__ == '__main__':
    run_identification()
