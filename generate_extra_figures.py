"""
生成补充图表:
  Fig 1: OCV-SOC 特性曲线
  Fig 2: 电压分量分解图 (V1 / V_sd / IR 贡献对比)
  Fig 3: SOC 估计误差分布直方图
  Fig 4: 方法论框架图 (改进模型 + UKF 流程图)
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from parameters import (
    Q_n, R0, R1, C1, tau1, tau_sd, K_sd,
    dt, SOC_init, generate_current_profile, ocv_soc_poly
)
from ukf import UKFEstimator

OUT_DIR = os.path.dirname(__file__)

# ==================== 字体设置 ====================
for font_name in ['SimHei', 'Microsoft YaHei', 'Noto Sans CJK SC', 'DejaVu Sans']:
    try:
        matplotlib.font_manager.findfont(font_name, fallback_to_default=False)
        plt.rcParams['font.sans-serif'] = [font_name]
        break
    except Exception:
        continue
plt.rcParams['axes.unicode_minus'] = False


# ============================================================
# Fig A: OCV-SOC 特性曲线
# ============================================================
def plot_ocv_soc():
    fig, ax = plt.subplots(figsize=(8, 5))
    soc = np.linspace(0, 1, 500)
    ocv = ocv_soc_poly(soc)

    ax.plot(soc * 100, ocv, 'b-', linewidth=2.0)
    ax.fill_between(soc * 100, ocv, ocv.min() - 0.05, alpha=0.06, color='blue')

    # 标注实验 SOC 范围
    ax.axvline(x=80, color='#e74c3c', linestyle='--', linewidth=1.2, alpha=0.7)
    ax.annotate('Initial SOC = 80%\n(experiment start)',
                xy=(80, ocv_soc_poly(0.80)), xytext=(55, 3.55),
                arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.2),
                fontsize=10, color='#c0392b', fontweight='bold')

    # 关键点标注
    for s, label in [(0, '0%\n(3.0V)'), (1, '100%\n(4.2V)')]:
        ax.plot(s * 100, ocv_soc_poly(s), 'ko', markersize=5)
        ax.annotate(label, xy=(s * 100, ocv_soc_poly(s)),
                    xytext=(s * 100 + 8, ocv_soc_poly(s) + (-0.15 if s == 0 else 0.12)),
                    fontsize=9, ha='center',
                    arrowprops=dict(arrowstyle='->', lw=0.8, color='gray'))

    ax.set_xlabel('SOC (%)', fontsize=12)
    ax.set_ylabel('OCV (V)', fontsize=12)
    ax.set_title('OCV-SOC Characteristic Curve\n'
                 r'$OCV(SOC)=0.9·SOC^3−1.5·SOC^2+1.8·SOC+3.0$',
                 fontsize=13, fontweight='bold')
    ax.set_xlim([-2, 102])
    ax.set_ylim([2.85, 4.35])
    ax.grid(True, alpha=0.3)
    ax.text(0.98, 0.04, 'NMC/Graphite chemistry', transform=ax.transAxes,
            fontsize=9, ha='right', va='bottom', style='italic', color='gray')

    fig.tight_layout()
    path = os.path.join(OUT_DIR, 'fig_ocv_soc.png')
    fig.savefig(path, dpi=200, bbox_inches='tight')
    print(f'  Saved: {path}')
    plt.close(fig)


# ============================================================
# Fig B: 电压分量分解图
# ============================================================
def plot_voltage_decomposition():
    """模拟一段充放电 + 静置，分解 Vt 的四个分量"""
    # 短工况: 放电300s → 静置600s → 充电300s
    t_total = 1200
    N = int(t_total / dt)
    t = np.arange(N) * dt

    I = np.zeros(N)
    I[0:3000] = 2.5        # 放电 300s
    I[3000:9000] = 0.0     # 静置 600s
    I[9000:12000] = -2.5   # 充电 300s

    # 真值模拟
    SOC = np.zeros(N)
    V1, Vsd = np.zeros(N), np.zeros(N)
    SOC[0] = SOC_init

    for k in range(N - 1):
        Ik = I[k]
        SOC[k+1] = SOC[k] - dt * Ik / Q_n
        V1[k+1]  = V1[k] * np.exp(-dt / tau1) + Ik * R1 * (1 - np.exp(-dt / tau1))
        Vsd[k+1] = Vsd[k] * np.exp(-dt / tau_sd) + Ik * K_sd * (1 - np.exp(-dt / tau_sd))

    SOC = np.clip(SOC, 0.0, 1.0)
    OCV = ocv_soc_poly(SOC)
    IR  = I * R0

    # 四面板
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)

    colors = {'OCV': '#2c3e50', 'V1': '#2980b9', 'Vsd': '#e74c3c', 'IR': '#27ae60'}

    # (a) Current
    ax = axes[0]
    ax.fill_between(t, I, 0, alpha=0.12, color='#2c3e50')
    ax.plot(t, I, 'k-', linewidth=0.8)
    ax.set_ylabel('Current (A)', fontsize=11)
    ax.axhline(y=0, color='gray', linewidth=0.5, linestyle=':')
    ax.grid(True, alpha=0.3)
    ax.text(0.01, 0.9, '(a) Load Current', transform=ax.transAxes,
            fontsize=11, fontweight='bold')

    # (b) OCV (slow drift due to SOC change)
    ax = axes[1]
    ax.plot(t, OCV, linewidth=1.5, color=colors['OCV'])
    ax.set_ylabel('OCV (V)', fontsize=11, color=colors['OCV'])
    ax.tick_params(axis='y', labelcolor=colors['OCV'])
    ax.grid(True, alpha=0.3)
    ax.text(0.01, 0.9, '(b) Open-Circuit Voltage', transform=ax.transAxes,
            fontsize=11, fontweight='bold')
    # highlight SOC-driven OCV change during discharge/charge
    ax.axvspan(0, 300, alpha=0.04, color='red', label='Discharge')
    ax.axvspan(900, 1200, alpha=0.04, color='green', label='Charge')

    # (c) Polarization voltages V1 and V_sd
    ax = axes[2]
    ax.plot(t, V1 * 1000, linewidth=1.5, color=colors['V1'],
            label=r'$V_1$ (EC polarization, $\tau_1$=37.5s)')
    ax.plot(t, Vsd * 1000, linewidth=1.5, color=colors['Vsd'],
            label=r'$V_{sd}$ (Solid diffusion, $\tau_{sd}$=280s)')
    ax.set_ylabel('Voltage (mV)', fontsize=11)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.text(0.01, 0.9, '(c) Polarization Components', transform=ax.transAxes,
            fontsize=11, fontweight='bold')

    # (d) IR drop
    ax = axes[3]
    ax.plot(t, IR * 1000, linewidth=1.5, color=colors['IR'])
    ax.set_ylabel(r'$I·R_0$ (mV)', fontsize=11, color=colors['IR'])
    ax.set_xlabel('Time (s)', fontsize=12)
    ax.tick_params(axis='y', labelcolor=colors['IR'])
    ax.grid(True, alpha=0.3)
    ax.text(0.01, 0.9, r'(d) Ohmic Drop ($I·R_0$)', transform=ax.transAxes,
            fontsize=11, fontweight='bold')

    fig.suptitle('Terminal Voltage Component Decomposition\n'
                 r'$V_t = OCV(SOC) - V_1 - V_{sd} - I·R_0$',
                 fontsize=14, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = os.path.join(OUT_DIR, 'fig_voltage_decomposition.png')
    fig.savefig(path, dpi=200, bbox_inches='tight')
    print(f'  Saved: {path}')
    plt.close(fig)


# ============================================================
# Fig C: SOC 误差分布直方图
# ============================================================
def plot_error_distribution():
    """从三模型对比仿真中获取误差数据并绘制直方图"""
    from run_p0 import run_three_way_comparison
    from parameters import generate_current_profile, SOC_init, Q_n, tau1, tau_sd, K_sd, R0, R1, ocv_soc_poly

    I = generate_current_profile(dt)
    N = len(I)
    t = np.arange(N) * dt

    # Truth
    SOC_true = np.zeros(N)
    V1_true, Vsd_true, Vt_true = np.zeros(N), np.zeros(N), np.zeros(N)
    SOC_true[0] = SOC_init
    for k in range(N - 1):
        Ik = I[k]
        SOC_true[k+1] = SOC_true[k] - dt * Ik / Q_n
        V1_true[k+1]  = V1_true[k] * np.exp(-dt / tau1) + Ik * R1 * (1 - np.exp(-dt / tau1))
        Vsd_true[k+1] = Vsd_true[k] * np.exp(-dt / tau_sd) + Ik * K_sd * (1 - np.exp(-dt / tau_sd))
    SOC_true = np.clip(SOC_true, 0.0, 1.0)
    for k in range(N):
        Vt_true[k] = ocv_soc_poly(SOC_true[k]) - V1_true[k] - Vsd_true[k] - I[k] * R0

    np.random.seed(42)
    sigma_v = 0.002
    Vt_meas = Vt_true + np.random.randn(N) * sigma_v

    # Three models
    R_ukf = np.array([[sigma_v**2]])
    ukf_trad = UKFEstimator('traditional', Q=np.diag([1e-8, 1e-6]), R=R_ukf)
    ukf_impr = UKFEstimator('improved', Q=np.diag([1e-8, 1e-6, 5e-7]), R=R_ukf)
    ukf_adpt = UKFEstimator('adaptive', Q=np.diag([1e-8, 1e-6, 1e-6, 0.002]), R=R_ukf)

    x_trad = np.array([SOC_init, 0.0])
    P_trad = np.diag([0.01**2, 0.01**2])
    x_impr = np.array([SOC_init, 0.0, 0.0])
    P_impr = np.diag([0.01**2, 0.01**2, 0.005**2])
    x_adpt = np.array([SOC_init, 0.0, 0.0, 300.0])
    P_adpt = np.diag([0.01**2, 0.01**2, 0.005**2, 30.0**2])

    SOC_est = {'Traditional': np.zeros(N), 'Improved': np.zeros(N), 'Adaptive': np.zeros(N)}
    SOC_est['Traditional'][0] = x_trad[0]
    SOC_est['Improved'][0] = x_impr[0]
    SOC_est['Adaptive'][0] = x_adpt[0]

    for k in range(N - 1):
        x_trad, P_trad = ukf_trad.step(x_trad, P_trad, I[k], I[k+1], Vt_meas[k+1], dt)
        x_impr, P_impr = ukf_impr.step(x_impr, P_impr, I[k], I[k+1], Vt_meas[k+1], dt)
        x_adpt, P_adpt = ukf_adpt.step(x_adpt, P_adpt, I[k], I[k+1], Vt_meas[k+1], dt)
        SOC_est['Traditional'][k+1] = x_trad[0]
        SOC_est['Improved'][k+1] = x_impr[0]
        SOC_est['Adaptive'][k+1] = x_adpt[0]

    # Compute errors
    errors = {}
    stats = {}
    for name in ['Traditional', 'Improved', 'Adaptive']:
        err = (SOC_est[name] - SOC_true) * 100
        errors[name] = err
        stats[name] = {
            'mean': np.mean(err), 'std': np.std(err),
            'skew': float(np.mean((err - np.mean(err))**3) / np.std(err)**3 if np.std(err) > 0 else 0),
            'rmse': np.sqrt(np.mean(err**2)),
            'mae': np.mean(np.abs(err)),
            'max': np.max(np.abs(err)),
        }

    # Plot
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=False)
    colors = {'Traditional': '#e74c3c', 'Improved': '#2980b9', 'Adaptive': '#27ae60'}
    bins = 60

    for ax, (name, err) in zip(axes, errors.items()):
        ax.hist(err, bins=bins, density=True, alpha=0.7, color=colors[name],
                edgecolor='white', linewidth=0.3)
        # Normal fit
        mu, sigma = stats[name]['mean'], stats[name]['std']
        x_fit = np.linspace(err.min(), err.max(), 200)
        y_fit = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_fit - mu) / sigma)**2)
        ax.plot(x_fit, y_fit, 'k-', linewidth=1.2, alpha=0.7)

        # Annotate stats
        s = stats[name]
        text = (f"Mean = {s['mean']:+.2f}%\n"
                f"Std  = {s['std']:.2f}%\n"
                f"RMSE = {s['rmse']:.2f}%\n"
                f"Max  = {s['max']:.2f}%")
        ax.text(0.97, 0.95, text, transform=ax.transAxes, fontsize=8.5,
                va='top', ha='right',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.85, ec='gray'))

        ax.axvline(x=0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)
        ax.axvline(x=mu, color='black', linestyle=':', linewidth=0.8, alpha=0.5)
        ax.set_xlabel('SOC Error (%)', fontsize=11)
        ax.set_title(f'{name} (n={("2","3","4")[list(errors.keys()).index(name)]})',
                     fontsize=12, fontweight='bold', color=colors[name])
        ax.set_ylabel('Probability Density', fontsize=10)
        ax.grid(True, alpha=0.2, axis='y')

    fig.suptitle('SOC Estimation Error Distribution Comparison\n'
                 'Histogram + Gaussian Fit',
                 fontsize=13, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    path = os.path.join(OUT_DIR, 'fig_error_distribution.png')
    fig.savefig(path, dpi=200, bbox_inches='tight')
    print(f'  Saved: {path}')
    plt.close(fig)


# ============================================================
# Fig D: 方法论框架图
# ============================================================
def plot_methodology():
    """方法论示意图: 改进ECM + UKF 估计框架"""
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.set_aspect('equal')

    # Helper to draw boxes
    def draw_box(x, y, w, h, text, color='#3498db', text_color='white', fontsize=10, fontweight='bold'):
        rect = FancyBboxPatch((x - w/2, y - h/2), w, h,
                              boxstyle="round,pad=0.15", facecolor=color,
                              edgecolor='#2c3e50', linewidth=1.5, alpha=0.92)
        ax.add_patch(rect)
        lines = text.split('\n')
        for j, line in enumerate(lines):
            is_sub = line.startswith('  ')
            ax.text(x, y + (len(lines)/2 - j - 0.5) * 0.42, line.replace('  ', ''),
                    ha='center', va='center', fontsize=fontsize - (2 if is_sub else 0),
                    color=text_color, fontweight=fontweight if not is_sub else 'normal')

    def draw_arrow(x1, y1, x2, y2, color='#2c3e50', lw=1.8, style='->'):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                    connectionstyle='arc3,rad=0'))

    def draw_label(x, y, text, fontsize=9, color='#2c3e50', ha='center'):
        ax.text(x, y, text, fontsize=fontsize, color=color, ha=ha, va='center',
                style='italic')

    # ===== Top Row: Battery + Measurements =====
    draw_box(2.5, 8.5, 3.2, 1.6, 'Li-ion Battery\nNMC/Graphite', '#2c3e50')
    draw_box(6.5, 8.5, 2.8, 1.6, 'Measurements\n  V_t, I, T', '#7f8c8d')
    draw_box(10.5, 8.5, 3.2, 1.6, 'OCV-SOC\nPolynomial Model', '#2c3e50')

    draw_arrow(4.2, 8.5, 5.0, 8.5)
    draw_arrow(8.0, 8.5, 8.8, 8.5)

    # ===== Middle Row: Improved ECM =====
    draw_box(6.5, 6.0, 10.0, 2.2,
             'Improved Equivalent Circuit Model\n'
             '  x = [SOC, V1, V_sd]^T\n'
             '  V_t = OCV(SOC) - V1 - V_sd - I*R0\n'
             '  NEW: G_sd(s) = K_sd/(tau_sd*s+1)  (Solid Diffusion Correction)',
             '#2980b9')

    draw_arrow(6.5, 7.6, 6.5, 7.0, '#2980b9', lw=2.2)

    # Left side: Parameter identification
    draw_box(1.2, 5.2, 2.4, 1.4,
             'Offline Parameter\nIdentification\n  Pulse-Relaxation\n  -> tau_sd, K_sd',
             '#8e44ad')
    draw_arrow(2.6, 5.6, 2.5, 5.6, '#8e44ad')
    draw_arrow(2.5, 5.6, 2.5, 6.5, '#8e44ad')
    draw_arrow(2.5, 6.5, 1.8, 6.5, '#8e44ad')
    # Arrow from param id to ECM
    draw_arrow(2.6, 5.2, 3.0, 5.8, '#8e44ad', style='->')

    # ===== Bottom Row: UKF =====
    draw_box(6.5, 3.2, 10.5, 2.4,
             'Unscented Kalman Filter (UKF)\n'
             '  (1) Sigma Points (2n+1) -> (2) State Prediction -> (3) Measurement Update\n'
             '  (4) Kalman Gain -> (5) State Correction\n'
             '  Q = diag(sigma2_SOC, sigma2_V1, sigma2_Vsd)   R = sigma2_v',
             '#e67e22')

    draw_arrow(6.5, 4.8, 6.5, 4.5, '#e67e22', lw=2.2)

    # Feedback arrow
    ax.annotate('', xy=(4.0, 6.0), xytext=(4.0, 3.2),
                arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.5,
                                connectionstyle='arc3,rad=0.3', linestyle='dashed'))
    ax.text(3.0, 4.6, 'Voltage\nInnovation\nFeedback', fontsize=7.5, color='#c0392b',
            ha='center', va='center', fontstyle='italic')

    # ===== Bottom: Output =====
    draw_box(6.5, 1.2, 4.0, 1.2, 'SOC Estimate\n  with Error Bounds', '#27ae60')

    draw_arrow(6.5, 2.0, 6.5, 1.8, '#27ae60', lw=2.2)

    # Legend-like annotations
    ax.text(0.3, 0.3, '●  Physical System', fontsize=8, color='#2c3e50',
            transform=ax.transAxes)
    ax.text(0.3, 0.22, '●  Model / Estimation', fontsize=8, color='#2980b9',
            transform=ax.transAxes)
    ax.text(0.3, 0.14, '●  Filter Algorithm', fontsize=8, color='#e67e22',
            transform=ax.transAxes)
    ax.text(0.3, 0.06, '●  Output / Result', fontsize=8, color='#27ae60',
            transform=ax.transAxes)

    fig.suptitle('Methodology Overview: Improved ECM + UKF Framework for SOC Estimation',
                 fontsize=14, fontweight='bold', y=0.96)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    path = os.path.join(OUT_DIR, 'fig_methodology.png')
    fig.savefig(path, dpi=200, bbox_inches='tight')
    print(f'  Saved: {path}')
    plt.close(fig)


# ============================================================
if __name__ == '__main__':
    print("Generating supplementary figures...")
    plot_ocv_soc()
    plot_voltage_decomposition()
    plot_error_distribution()
    plot_methodology()
    print("All figures generated.")
