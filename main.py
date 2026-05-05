"""
主仿真脚本：提升一阶RC模型SOC估算精度的验证研究
=====================================================
对照组: 传统一阶RC模型 + UKF
实验组: 改进模型(固相扩散修正) + UKF

评估指标: 端电压拟合偏差、SOC最大误差、平均误差、RMSE

实验设计：
- "真实电池" 用改进模型模拟 (含固相扩散V_sd效应)
- 传统UKF忽略V_sd → 静置阶段出现SOC漂移
- 改进UKF包含V_sd → 准确追踪SOC
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from parameters import (
    Q_n, R0, R1, C1, tau1, tau_sd, K_sd,
    dt, SOC_init, generate_current_profile, ocv_soc_poly
)
from ukf import UKFEstimator

# ==================== 仿真主流程 ====================
def run_simulation():
    print("=" * 60)
    print("  锂电池SOC估计对比仿真：传统模型 vs 改进模型")
    print("=" * 60)

    # ---- 1. 生成工况电流 ----
    I_profile = generate_current_profile(dt)
    N = len(I_profile)
    t = np.arange(N) * dt
    print(f"\n[1] 工况生成: {N} 步, 总时长 {N*dt:.0f}s = {N*dt/60:.1f}min")

    # ---- 2. "真实电池" 模拟 (改进模型作为真值) ----
    SOC_true    = np.zeros(N)
    V1_true     = np.zeros(N)
    Vsd_true    = np.zeros(N)
    Vt_true     = np.zeros(N)

    SOC_true[0] = SOC_init
    V1_true[0]  = 0.0
    Vsd_true[0] = 0.0

    for k in range(N - 1):
        Ik = I_profile[k]
        # 欧拉离散 (同改进模型结构)
        SOC_true[k+1] = SOC_true[k] - dt * Ik / Q_n
        V1_true[k+1]  = V1_true[k] * np.exp(-dt / tau1) \
                        + Ik * R1 * (1 - np.exp(-dt / tau1))
        Vsd_true[k+1] = Vsd_true[k] * np.exp(-dt / tau_sd) \
                        + Ik * K_sd * (1 - np.exp(-dt / tau_sd))

    SOC_true = np.clip(SOC_true, 0.0, 1.0)
    for k in range(N):
        Vt_true[k] = ocv_soc_poly(SOC_true[k]) - V1_true[k] \
                     - Vsd_true[k] - I_profile[k] * R0

    # 添加测量噪声 (仅电压，电流用真值以隔离模型误差)
    np.random.seed(42)
    sigma_v = 0.002   # 电压噪声标准差 2mV
    Vt_meas = Vt_true + np.random.randn(N) * sigma_v
    I_sim   = I_profile.copy()  # UKF使用真实电流，排除电流噪声干扰

    print(f"[2] 真实电池仿真完成 (含固相扩散效应 V_sd)")

    # ---- 3. UKF初始化 ----
    # 传统模型UKF
    x_trad = np.array([SOC_init, 0.0])
    P_trad = np.diag([0.01**2, 0.01**2])
    Q_trad = np.diag([1e-8, 1e-6])
    R_ukf  = np.array([[sigma_v**2]])

    ukf_trad = UKFEstimator(model_type='traditional', Q=Q_trad, R=R_ukf)

    # 改进模型UKF
    x_impr = np.array([SOC_init, 0.0, 0.0])
    P_impr = np.diag([0.01**2, 0.01**2, 0.005**2])
    Q_impr = np.diag([1e-8, 1e-6, 5e-7])

    ukf_impr = UKFEstimator(model_type='improved', Q=Q_impr, R=R_ukf)

    # 存储估计结果
    SOC_est_trad = np.zeros(N)
    V1_est_trad  = np.zeros(N)
    SOC_est_impr = np.zeros(N)
    V1_est_impr  = np.zeros(N)
    Vsd_est_impr = np.zeros(N)
    Vt_est_trad  = np.zeros(N)
    Vt_est_impr  = np.zeros(N)

    SOC_est_trad[0] = x_trad[0]
    V1_est_trad[0]  = x_trad[1]
    SOC_est_impr[0] = x_impr[0]
    V1_est_impr[0]  = x_impr[1]
    Vsd_est_impr[0] = x_impr[2]

    # 初始端电压估计
    Vt_est_trad[0] = ocv_soc_poly(x_trad[0]) - x_trad[1] - I_sim[0]*R0
    Vt_est_impr[0] = ocv_soc_poly(x_impr[0]) - x_impr[1] \
                     - x_impr[2] - I_sim[0]*R0

    # ---- 4. UKF在线估计循环 ----
    print(f"[3] UKF在线估计中...")
    for k in range(N - 1):
        x_trad, P_trad = ukf_trad.step(x_trad, P_trad,
                                       I_sim[k], I_sim[k+1], Vt_meas[k+1], dt)
        x_impr, P_impr = ukf_impr.step(x_impr, P_impr,
                                       I_sim[k], I_sim[k+1], Vt_meas[k+1], dt)

        SOC_est_trad[k+1] = x_trad[0]
        V1_est_trad[k+1]  = x_trad[1]
        SOC_est_impr[k+1] = x_impr[0]
        V1_est_impr[k+1]  = x_impr[1]
        Vsd_est_impr[k+1] = x_impr[2]

        Vt_est_trad[k+1] = ocv_soc_poly(x_trad[0]) - x_trad[1] \
                           - I_sim[k+1]*R0
        Vt_est_impr[k+1] = ocv_soc_poly(x_impr[0]) - x_impr[1] \
                           - x_impr[2] - I_sim[k+1]*R0

    print(f"   传统模型UKF 完成")
    print(f"   改进模型UKF 完成")

    # ---- 5. 误差计算 ----
    error_trad = SOC_est_trad - SOC_true
    error_impr = SOC_est_impr - SOC_true

    metrics_trad = {
        'max_error': np.max(np.abs(error_trad)) * 100,
        'mean_error': np.mean(np.abs(error_trad)) * 100,
        'rmse': np.sqrt(np.mean(error_trad**2)) * 100,
    }
    metrics_impr = {
        'max_error': np.max(np.abs(error_impr)) * 100,
        'mean_error': np.mean(np.abs(error_impr)) * 100,
        'rmse': np.sqrt(np.mean(error_impr**2)) * 100,
    }

    # 端电压误差
    vt_error_trad = Vt_est_trad - Vt_true
    vt_error_impr = Vt_est_impr - Vt_true
    vt_rmse_trad = np.sqrt(np.mean(vt_error_trad**2)) * 1000  # mV
    vt_rmse_impr = np.sqrt(np.mean(vt_error_impr**2)) * 1000

    # ---- 6. 结果输出 ----
    # 判断是否达标
    def check_metrics(m):
        return [m['max_error'] <= 1.5, m['mean_error'] <= 0.8, m['rmse'] <= 1.0]

    checks_trad = check_metrics(metrics_trad)
    checks_impr = check_metrics(metrics_impr)

    print(f"\n{'='*70}")
    print(f"  SOC Estimation Error Comparison")
    print(f"{'='*70}")
    print(f"{'Metric':<20}{'Traditional':>14}{'Improved':>14}{'Target':>12}")
    print(f"{'-'*70}")
    print(f"{'Max Error (%)':<20}{metrics_trad['max_error']:>14.4f}"
          f"{metrics_impr['max_error']:>14.4f}{'<=1.5':>12}")
    print(f"{'Mean Error (%)':<20}{metrics_trad['mean_error']:>14.4f}"
          f"{metrics_impr['mean_error']:>14.4f}{'<=0.8':>12}")
    print(f"{'RMSE (%)':<20}{metrics_trad['rmse']:>14.4f}"
          f"{metrics_impr['rmse']:>14.4f}{'<=1.0':>12}")
    print(f"{'-'*70}")
    print(f"{'Vt RMSE (mV)':<20}{vt_rmse_trad:>14.4f}"
          f"{vt_rmse_impr:>14.4f}")
    print(f"{'='*70}")

    # 达标判定 (双模型)
    labels = ['Max Error', 'Mean Error', 'RMSE']
    print(f"\n{'Model':<20}{'Max Error':>12}{'Mean Error':>12}{'RMSE':>12}{'Status':>10}")
    print(f"{'-'*66}")
    for name, checks in [('Traditional', checks_trad), ('Improved', checks_impr)]:
        marks = ''.join([' P' if c else ' F' for c in checks])
        status = 'ALL PASS' if all(checks) else f'{sum(checks)}/3 PASS'
        print(f"{name:<20}{marks[1:4]:>12}{marks[5:8]:>12}{marks[9:]:>12}{status:>10}")
    print(f"{'-'*66}")

    # ---- 7. 可视化 ----
    print(f"\n[4] 生成论文用图...")
    plot_results(t, I_profile, Vt_true, Vt_meas,
                 Vt_est_trad, Vt_est_impr,
                 SOC_true, SOC_est_trad, SOC_est_impr,
                 error_trad, error_impr,
                 V1_true, V1_est_trad, V1_est_impr,
                 Vsd_true, Vsd_est_impr,
                 metrics_trad, metrics_impr, vt_rmse_trad, vt_rmse_impr)

    return (metrics_trad, metrics_impr, checks_trad, checks_impr)


# ==================== 可视化函数 ====================
def plot_results(t, I, Vt_true, Vt_meas,
                 Vt_est_trad, Vt_est_impr,
                 SOC_true, SOC_est_trad, SOC_est_impr,
                 error_trad, error_impr,
                 V1_true, V1_est_trad, V1_est_impr,
                 Vsd_true, Vsd_est_impr,
                 metrics_trad, metrics_impr, vt_rmse_trad, vt_rmse_impr):
    """生成论文用对比图 (中文字体适配)"""

    # 字体设置
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.unicode_minus'] = False

    # 尝试设置中文字体
    for font_name in ['SimHei', 'Microsoft YaHei', 'Noto Sans CJK SC',
                       'WenQuanYi Micro Hei', 'DejaVu Sans']:
        try:
            matplotlib.font_manager.findfont(font_name, fallback_to_default=False)
            plt.rcParams['font.sans-serif'] = [font_name]
            break
        except Exception:
            continue

    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.suptitle('锂离子电池 SOC 估算对比：传统一阶RC模型 vs 改进模型(固相扩散修正)',
                 fontsize=13, fontweight='bold', y=0.98)

    t_min = t / 60.0  # 转换为分钟

    # ---- (a) 电流工况 ----
    ax = axes[0, 0]
    ax.plot(t_min, I, linewidth=0.8, color='#2c3e50')
    ax.fill_between(t_min, I, 0, alpha=0.08, color='#2c3e50')
    ax.axhline(y=0, color='gray', linestyle=':', linewidth=0.6)
    ax.set_ylabel('Current (A)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(a) Current Profile', fontweight='bold')
    ax.set_ylim([-3.5, 3.5])
    ax.grid(True, alpha=0.3)

    # ---- (b) 端电压对比 ----
    ax = axes[0, 1]
    ax.plot(t_min, Vt_true, linewidth=0.5, color='gray', alpha=0.6, label='True Vt')
    ax.plot(t_min, Vt_est_trad, linewidth=1.2, color='#e74c3c',
            label=f'Traditional (RMSE={vt_rmse_trad:.2f} mV)')
    ax.plot(t_min, Vt_est_impr, linewidth=1.2, color='#2980b9',
            label=f'Improved (RMSE={vt_rmse_impr:.2f} mV)', linestyle='--')
    ax.set_ylabel('Terminal Voltage (V)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(b) Terminal Voltage Estimation', fontweight='bold')
    ax.legend(fontsize=8, loc='best')
    ax.grid(True, alpha=0.3)

    # ---- (c) SOC估计对比 ----
    ax = axes[1, 0]
    ax.plot(t_min, SOC_true * 100, linewidth=2.0, color='black',
            label='True SOC', zorder=3)
    ax.plot(t_min, SOC_est_trad * 100, linewidth=1.2, color='#e74c3c',
            label=f'Trad (MAE={metrics_trad["mean_error"]:.2f}%)', alpha=0.85)
    ax.plot(t_min, SOC_est_impr * 100, linewidth=1.2, color='#2980b9',
            label=f'Impr (MAE={metrics_impr["mean_error"]:.2f}%)',
            linestyle='--', alpha=0.85)
    ax.set_ylabel('SOC (%)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(c) SOC Estimation Comparison', fontweight='bold')
    ax.legend(fontsize=8, loc='best')
    ax.grid(True, alpha=0.3)
    ax.set_ylim([10, 90])

    # ---- (d) SOC估计误差 ----
    ax = axes[1, 1]
    ax.plot(t_min, error_trad * 100, linewidth=1.0, color='#e74c3c',
            label=f'Traditional (RMSE={metrics_trad["rmse"]:.2f}%)')
    ax.plot(t_min, error_impr * 100, linewidth=1.0, color='#2980b9',
            label=f'Improved (RMSE={metrics_impr["rmse"]:.2f}%)',
            linestyle='--')
    ax.axhline(y=0, color='black', linestyle=':', linewidth=0.6)
    # 目标区间
    ax.axhspan(-1.5, 1.5, alpha=0.06, color='green', label='Target (±1.5%)')
    ax.set_ylabel('SOC Error (%)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(d) SOC Estimation Error', fontweight='bold')
    ax.legend(fontsize=8, loc='best')
    ax.grid(True, alpha=0.3)

    # ---- (e) V_sd 估计与真值对比 ----
    ax = axes[2, 0]
    ax.plot(t_min, Vsd_true * 1000, linewidth=1.5, color='black',
            label='True V_sd')
    ax.plot(t_min, Vsd_est_impr * 1000, linewidth=1.2, color='#2980b9',
            linestyle='--', label='Estimated V_sd')
    ax.set_ylabel('V_sd (mV)')
    ax.set_xlabel('Time (min)')
    ax.set_title('(e) Solid-Phase Diffusion Voltage V_sd', fontweight='bold')
    ax.legend(fontsize=8, loc='best')
    ax.grid(True, alpha=0.3)

    # ---- (f) 误差统计柱状图 ----
    ax = axes[2, 1]
    labels = ['Max Error\n(%)', 'Mean Error\n(%)', 'RMSE\n(%)']
    x = np.arange(len(labels))
    width = 0.35
    bars1 = ax.bar(x - width/2,
                   [metrics_trad['max_error'], metrics_trad['mean_error'],
                    metrics_trad['rmse']],
                   width, label='Traditional', color='#e74c3c', alpha=0.85)
    bars2 = ax.bar(x + width/2,
                   [metrics_impr['max_error'], metrics_impr['mean_error'],
                    metrics_impr['rmse']],
                   width, label='Improved', color='#2980b9', alpha=0.85)
    # 目标线
    targets = [1.5, 0.8, 1.0]
    for i, (xi, target) in enumerate(zip(x, targets)):
        ax.axhline(y=target, xmin=xi/3 - 0.05, xmax=xi/3 + 0.3,
                   color='green', linestyle='--', linewidth=1.2)
        ax.annotate(f'{target}%', xy=(xi + 0.25, target),
                    fontsize=8, color='green', va='bottom')

    # 在柱上标数值
    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 0.03,
                f'{h:.2f}', ha='center', fontsize=8, color='#c0392b')
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 0.03,
                f'{h:.2f}', ha='center', fontsize=8, color='#2471a3')

    ax.set_ylabel('Error (%)')
    ax.set_title('(f) Error Metrics Comparison', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(fontsize=8, loc='upper left')
    ax.grid(True, alpha=0.2, axis='y')

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = os.path.join(os.path.dirname(__file__), 'comparison_results.png')
    fig.savefig(out_path, dpi=200, bbox_inches='tight')
    print(f"   图表已保存: {out_path}")
    plt.close(fig)

    # ---- 补充：静置阶段局部放大图 ----
    fig2, axes2 = plt.subplots(1, 2, figsize=(12, 4.5))
    fig2.suptitle('静置阶段 SOC 漂移对比 (局部放大)', fontsize=12,
                  fontweight='bold')

    # 找到第一个静置区间的索引 (放电结束 → 静置结束)
    rest_start = int(1500 / dt)
    rest_end   = int(2400 / dt)
    # 扩展范围以包含过渡区
    zoom_start = max(0, rest_start - int(100 / dt))
    zoom_end   = min(len(t), rest_end + int(100 / dt))

    ax = axes2[0]
    ax.plot(t_min[zoom_start:zoom_end],
            SOC_true[zoom_start:zoom_end] * 100,
            linewidth=2.0, color='black', label='True SOC')
    ax.plot(t_min[zoom_start:zoom_end],
            SOC_est_trad[zoom_start:zoom_end] * 100,
            linewidth=1.2, color='#e74c3c', label='Traditional')
    ax.plot(t_min[zoom_start:zoom_end],
            SOC_est_impr[zoom_start:zoom_end] * 100,
            linewidth=1.2, color='#2980b9', linestyle='--', label='Improved')
    ax.set_ylabel('SOC (%)')
    ax.set_xlabel('Time (min)')
    ax.set_title('SOC During Rest Period', fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes2[1]
    ax.plot(t_min[zoom_start:zoom_end],
            Vt_true[zoom_start:zoom_end],
            linewidth=1.5, color='black', label='True Vt')
    ax.plot(t_min[zoom_start:zoom_end],
            Vt_est_trad[zoom_start:zoom_end],
            linewidth=1.0, color='#e74c3c', label='Traditional')
    ax.plot(t_min[zoom_start:zoom_end],
            Vt_est_impr[zoom_start:zoom_end],
            linewidth=1.0, color='#2980b9', linestyle='--', label='Improved')
    ax.set_ylabel('Terminal Voltage (V)')
    ax.set_xlabel('Time (min)')
    ax.set_title('Voltage Relaxation During Rest', fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path2 = os.path.join(os.path.dirname(__file__),
                             'rest_period_detail.png')
    fig2.savefig(out_path2, dpi=200, bbox_inches='tight')
    print(f"   图表已保存: {out_path2}")
    plt.close(fig2)


# ==================== 入口 ====================
if __name__ == '__main__':
    metrics_trad, metrics_impr, checks_trad, checks_impr = run_simulation()

    # 结论
    print(f"\n{'='*70}")
    print(f"  CONCLUSION")
    print(f"{'='*70}")
    if all(checks_impr) and not all(checks_trad):
        print("  Traditional model FAILS targets -> demonstrates need for improvement.")
        print("  Improved model PASSES all targets -> validates the proposed method.")
    elif all(checks_impr):
        print("  Both models pass targets. Improved model shows significant advantage.")
    else:
        print("  Some targets not met. Consider parameter tuning.")

    imp = {}
    for key in ['max_error', 'mean_error', 'rmse']:
        imp[key] = (metrics_trad[key] - metrics_impr[key]) / metrics_trad[key] * 100

    print(f"\n  Improvement from proposed method:")
    print(f"    Max Error:  {imp['max_error']:+.1f}%")
    print(f"    Mean Error: {imp['mean_error']:+.1f}%")
    print(f"    RMSE:       {imp['rmse']:+.1f}%")
    print(f"{'='*70}")
