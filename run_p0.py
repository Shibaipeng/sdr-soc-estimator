"""
P0 综合对比实验
===============
三模型对比:
  1. 传统一阶RC + UKF      (对照组 baseline)
  2. 改进模型  + UKF       (论文方案, 固定 tau_sd)
  3. 自适应模型 + UKF      (P0-1 突破, tau_sd 在线估计)

+ P0-2 参数离线辨识结果汇总

工况: 1C放电 → 静置 → 1C充电 → 静置
评估: SOC 最大误差 / 平均误差 / RMSE
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from parameters import (
    Q_n, R0, R1, C1, tau1, tau_sd, K_sd,
    dt, SOC_init, generate_current_profile, ocv_soc_poly
)
from ukf import UKFEstimator
from param_identify import run_identification


# ==================== 主仿真 ====================
def run_three_way_comparison():
    print("=" * 70)
    print("  P0: 3-Model Comparison")
    print("  Traditional vs Improved vs Adaptive UKF")
    print("=" * 70)

    I = generate_current_profile(dt)
    N = len(I)
    t = np.arange(N) * dt
    print(f"\n[Setup] {N} steps, {N*dt:.0f}s ({N*dt/60:.0f}min)")

    # ---- Truth (改进模型含 V_sd) ----
    SOC_true = np.zeros(N)
    V1_true, Vsd_true, Vt_true = np.zeros(N), np.zeros(N), np.zeros(N)
    SOC_true[0] = SOC_init

    for k in range(N - 1):
        Ik = I[k]
        SOC_true[k+1] = SOC_true[k] - dt * Ik / Q_n
        V1_true[k+1]  = V1_true[k] * np.exp(-dt / tau1) \
                        + Ik * R1 * (1 - np.exp(-dt / tau1))
        Vsd_true[k+1] = Vsd_true[k] * np.exp(-dt / tau_sd) \
                        + Ik * K_sd * (1 - np.exp(-dt / tau_sd))
    SOC_true = np.clip(SOC_true, 0.0, 1.0)
    for k in range(N):
        Vt_true[k] = ocv_soc_poly(SOC_true[k]) - V1_true[k] \
                     - Vsd_true[k] - I[k] * R0

    np.random.seed(42)
    sigma_v = 0.002
    Vt_meas = Vt_true + np.random.randn(N) * sigma_v

    print(f"[Truth] V_sd range: {Vsd_true.min()*1000:.1f} to {Vsd_true.max()*1000:.1f} mV")
    print(f"[Noise] Voltage: {sigma_v*1000:.1f}mV RMS")

    # ---- 三模型初始化 ----
    R_ukf = np.array([[sigma_v**2]])

    # 传统
    ukf_trad = UKFEstimator('traditional',
                            Q=np.diag([1e-8, 1e-6]), R=R_ukf)
    # 改进 (固定 tau_sd)
    ukf_impr = UKFEstimator('improved',
                            Q=np.diag([1e-8, 1e-6, 5e-7]), R=R_ukf)
    # 自适应 (tau_sd 在线估计)
    # τ_sd 极慢随机游走 — 由 P0-2 离线辨识初始化, 仅做微调
    Q_adapt = np.diag([1e-8, 1e-6, 1e-6, 0.002])
    ukf_adpt = UKFEstimator('adaptive', Q=Q_adapt, R=R_ukf)

    # 状态
    x_trad = np.array([SOC_init, 0.0])
    P_trad = np.diag([0.01**2, 0.01**2])
    x_impr = np.array([SOC_init, 0.0, 0.0])
    P_impr = np.diag([0.01**2, 0.01**2, 0.005**2])
    # 自适应: 初始 τ_sd 故意给偏差值 (350s vs 真值 280s)
    x_adpt = np.array([SOC_init, 0.0, 0.0, 300.0])  # P0-2 离线辨识值
    P_adpt = np.diag([0.01**2, 0.01**2, 0.005**2, 30.0**2])

    # 存储
    SOC_est = {m: np.zeros(N) for m in ['trad', 'impr', 'adpt']}
    Vsd_est_impr = np.zeros(N)
    Vsd_est_adpt = np.zeros(N)
    tau_est_adpt = np.zeros(N)
    Vt_est = {m: np.zeros(N) for m in ['trad', 'impr', 'adpt']}

    SOC_est['trad'][0] = x_trad[0]
    SOC_est['impr'][0] = x_impr[0]
    SOC_est['adpt'][0] = x_adpt[0]
    Vsd_est_impr[0] = 0.0
    Vsd_est_adpt[0] = 0.0
    tau_est_adpt[0] = x_adpt[3]
    Vt_est['trad'][0] = ocv_soc_poly(x_trad[0]) - x_trad[1] - I[0]*R0
    Vt_est['impr'][0] = ocv_soc_poly(x_impr[0]) - x_impr[1] - x_impr[2] - I[0]*R0
    Vt_est['adpt'][0] = ocv_soc_poly(x_adpt[0]) - x_adpt[1] - x_adpt[2] - I[0]*R0

    # ---- UKF 在线估计 ----
    print(f"\n[UKF] Estimating...")
    for k in range(N - 1):
        x_trad, P_trad = ukf_trad.step(x_trad, P_trad, I[k], I[k+1], Vt_meas[k+1], dt)
        x_impr, P_impr = ukf_impr.step(x_impr, P_impr, I[k], I[k+1], Vt_meas[k+1], dt)
        x_adpt, P_adpt = ukf_adpt.step(x_adpt, P_adpt, I[k], I[k+1], Vt_meas[k+1], dt)

        SOC_est['trad'][k+1] = x_trad[0]
        SOC_est['impr'][k+1] = x_impr[0]
        SOC_est['adpt'][k+1] = x_adpt[0]
        Vsd_est_impr[k+1] = x_impr[2]
        Vsd_est_adpt[k+1] = x_adpt[2]
        tau_est_adpt[k+1] = x_adpt[3]

        Vt_est['trad'][k+1] = ocv_soc_poly(x_trad[0]) - x_trad[1] - I[k+1]*R0
        Vt_est['impr'][k+1] = ocv_soc_poly(x_impr[0]) - x_impr[1] - x_impr[2] - I[k+1]*R0
        Vt_est['adpt'][k+1] = ocv_soc_poly(x_adpt[0]) - x_adpt[1] - x_adpt[2] - I[k+1]*R0

    # ---- 误差计算 ----
    def compute_metrics(soc_est):
        err = soc_est - SOC_true
        return {
            'max': np.max(np.abs(err)) * 100,
            'mean': np.mean(np.abs(err)) * 100,
            'rmse': np.sqrt(np.mean(err**2)) * 100,
        }

    M = {m: compute_metrics(SOC_est[m]) for m in ['trad', 'impr', 'adpt']}

    # Vt RMSE
    vt_rmse = {}
    for m in ['trad', 'impr', 'adpt']:
        vt_rmse[m] = np.sqrt(np.mean((Vt_est[m] - Vt_true)**2)) * 1000

    # ---- 输出 ----
    print(f"\n{'='*70}")
    print(f"  SOC Estimation Error Comparison")
    print(f"{'='*70}")
    print(f"{'Model':<18}{'Max Error %':>12}{'Mean Error %':>12}{'RMSE %':>12}{'Vt RMSE mV':>12}")
    print(f"{'-'*66}")
    for name, key in [('Traditional', 'trad'), ('Improved', 'impr'), ('Adaptive', 'adpt')]:
        m = M[key]
        print(f"{name:<18}{m['max']:>12.4f}{m['mean']:>12.4f}{m['rmse']:>12.4f}"
              f"{vt_rmse[key]:>12.4f}")
    print(f"{'-'*66}")

    # 达标判断
    targets = {'max': 1.5, 'mean': 0.8, 'rmse': 1.0}
    print(f"\n{'Target Check':<18}{'Max≤1.5%':>12}{'Mean≤0.8%':>12}{'RMSE≤1.0%':>12}{'Status':>10}")
    print(f"{'-'*64}")
    for name, key in [('Traditional', 'trad'), ('Improved', 'impr'), ('Adaptive', 'adpt')]:
        m = M[key]
        passes = [m['max'] <= 1.5, m['mean'] <= 0.8, m['rmse'] <= 1.0]
        marks = ''.join([' P' if p else ' F' for p in passes])
        status = 'ALL PASS' if all(passes) else f'{sum(passes)}/3 PASS'
        print(f"{name:<18}{marks[1:4]:>12}{marks[5:8]:>12}{marks[9:]:>12}{status:>10}")

    # τ_sd 收敛分析
    tau_final = tau_est_adpt[-1]
    tau_err = abs(tau_final - tau_sd) / tau_sd * 100
    print(f"\n[Adaptive tau_sd] Initial: 300s, Final: {tau_final:.1f}s, "
          f"True: {tau_sd:.0f}s, Error: {tau_err:.1f}%")

    # ---- 可视化 ----
    plot_three_way(t, I, Vt_true, Vt_meas, Vt_est,
                   SOC_true, SOC_est, Vsd_true, Vsd_est_impr, Vsd_est_adpt,
                   tau_est_adpt, M, vt_rmse)

    return M, tau_est_adpt


def plot_three_way(t, I, Vt_true, Vt_meas, Vt_est,
                   SOC_true, SOC_est, Vsd_true, Vsd_impr, Vsd_adpt,
                   tau_adpt, M, vt_rmse):
    """三模型对比图"""
    for font_name in ['SimHei', 'Microsoft YaHei', 'Noto Sans CJK SC', 'DejaVu Sans']:
        try:
            matplotlib.font_manager.findfont(font_name, fallback_to_default=False)
            plt.rcParams['font.sans-serif'] = [font_name]
            break
        except Exception:
            continue

    fig, axes = plt.subplots(3, 2, figsize=(15, 13))
    fig.suptitle('Three-Model SOC Estimation Comparison\n'
                 'Traditional vs Improved vs Adaptive UKF',
                 fontsize=14, fontweight='bold')

    t_min = t / 60
    colors = {'trad': '#e74c3c', 'impr': '#2980b9', 'adpt': '#27ae60'}

    # (a) Current profile
    ax = axes[0, 0]
    ax.plot(t_min, I, linewidth=0.8, color='#2c3e50')
    ax.fill_between(t_min, I, 0, alpha=0.08)
    ax.set_ylabel('Current (A)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(a) Current Profile')
    ax.grid(True, alpha=0.3)

    # (b) Terminal voltage
    ax = axes[0, 1]
    ax.plot(t_min, Vt_true, linewidth=0.5, color='gray', alpha=0.5, label='True')
    ax.plot(t_min, Vt_est['trad'], linewidth=0.8, color=colors['trad'],
            label=f"Trad ({vt_rmse['trad']:.1f}mV)")
    ax.plot(t_min, Vt_est['impr'], linewidth=0.8, color=colors['impr'],
            linestyle='--', label=f"Impr ({vt_rmse['impr']:.1f}mV)")
    ax.plot(t_min, Vt_est['adpt'], linewidth=0.8, color=colors['adpt'],
            linestyle=':', label=f"Adpt ({vt_rmse['adpt']:.1f}mV)")
    ax.set_ylabel('Terminal Voltage (V)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(b) Terminal Voltage Estimation')
    ax.legend(fontsize=7, loc='best')
    ax.grid(True, alpha=0.3)

    # (c) SOC estimation
    ax = axes[1, 0]
    ax.plot(t_min, SOC_true * 100, 'k-', linewidth=2.0, label='True SOC', zorder=4)
    ax.plot(t_min, SOC_est['trad'] * 100, linewidth=1.0, color=colors['trad'],
            label=f"Trad (MAE={M['trad']['mean']:.2f}%)")
    ax.plot(t_min, SOC_est['impr'] * 100, linewidth=1.0, color=colors['impr'],
            linestyle='--', label=f"Impr (MAE={M['impr']['mean']:.2f}%)")
    ax.plot(t_min, SOC_est['adpt'] * 100, linewidth=1.0, color=colors['adpt'],
            linestyle=':', label=f"Adpt (MAE={M['adpt']['mean']:.2f}%)")
    ax.set_ylabel('SOC (%)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(c) SOC Estimation Comparison')
    ax.legend(fontsize=7, loc='best')
    ax.grid(True, alpha=0.3)

    # (d) SOC error
    ax = axes[1, 1]
    for key, name in [('trad', 'Traditional'), ('impr', 'Improved'), ('adpt', 'Adaptive')]:
        err = (SOC_est[key] - SOC_true) * 100
        ax.plot(t_min, err, linewidth=0.8, color=colors[key],
                label=f"{name} (RMSE={M[key]['rmse']:.2f}%)")
    ax.axhline(y=0, color='black', linestyle=':', linewidth=0.6)
    ax.axhspan(-1.5, 1.5, alpha=0.05, color='green', label='Target +-1.5%')
    ax.set_ylabel('SOC Error (%)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(d) SOC Estimation Error')
    ax.legend(fontsize=7, loc='best')
    ax.grid(True, alpha=0.3)

    # (e) V_sd tracking + tau_sd convergence
    ax = axes[2, 0]
    ax.plot(t_min, Vsd_true * 1000, 'k-', linewidth=1.5, label='True V_sd')
    ax.plot(t_min, Vsd_impr * 1000, linewidth=1.0, color=colors['impr'],
            linestyle='--', label='Improved V_sd')
    ax.plot(t_min, Vsd_adpt * 1000, linewidth=1.0, color=colors['adpt'],
            linestyle=':', label='Adaptive V_sd')
    ax.set_ylabel('V_sd (mV)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(e) V_sd Tracking')
    ax.legend(fontsize=7, loc='best')
    ax.grid(True, alpha=0.3)

    # (f) tau_sd online adaptation
    ax = axes[2, 1]
    ax.plot(t_min, tau_adpt, linewidth=1.2, color=colors['adpt'], label='Estimated tau_sd')
    ax.axhline(y=tau_sd, color='black', linestyle='--', linewidth=1.2,
               label=f'True tau_sd = {tau_sd:.0f}s')
    ax.fill_between(t_min, tau_sd * 0.8, tau_sd * 1.2, alpha=0.06, color='green',
                    label='+/-20% band')
    ax.set_ylabel('tau_sd (s)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(f) Online tau_sd Adaptation')
    ax.legend(fontsize=7, loc='best')
    ax.grid(True, alpha=0.3)
    ax.set_ylim([100, 500])

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = os.path.join(os.path.dirname(__file__), 'three_way_comparison.png')
    fig.savefig(out_path, dpi=200, bbox_inches='tight')
    print(f"\n  Figure saved: {out_path}")
    plt.close(fig)


# ==================== 入口 ====================
if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("  P0 BREAKTHROUGH EXPERIMENTS")
    print("=" * 70)

    # ---- Part A: 三模型 SOC 估计对比 ----
    print("\n" + "—" * 70)
    print("  PART A: Three-Model SOC Estimation")
    print("—" * 70)
    M, tau_adpt = run_three_way_comparison()

    # ---- Part B: 参数离线辨识 ----
    print("\n" + "—" * 70)
    print("  PART B: Offline Parameter Identification")
    print("—" * 70)
    tau_id, K_id, err_tau, err_K = run_identification()

    # ---- 总结 ----
    print("\n" + "=" * 70)
    print("  P0 SUMMARY")
    print("=" * 70)
    print(f"""
  P0-1 (Adaptive UKF):
    - Traditional model: {M['trad']['max']:.2f}% max, {M['trad']['rmse']:.2f}% RMSE
    - Improved model:    {M['impr']['max']:.2f}% max, {M['impr']['rmse']:.2f}% RMSE
    - Adaptive model:    {M['adpt']['max']:.2f}% max, {M['adpt']['rmse']:.2f}% RMSE
    - tau_sd converged to {tau_adpt[-1]:.0f}s (true: {tau_sd:.0f}s)

  P0-2 (Parameter Identification):
    - tau_sd: {tau_id:.1f}s (true: {tau_sd:.0f}s, error: {err_tau:.1f}%)
    - K_sd:   {K_id:.4f} (true: {K_sd:.4f}, error: {err_K:.1f}%)
""")
    print("=" * 70)
