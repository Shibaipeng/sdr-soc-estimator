"""
Generate methodology framework figure — drawio-inspired style.
Sharp dashed containers, vertical side labels, orthogonal edges, pastel palette.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
import matplotlib.patches as mpatches
import numpy as np
import os

OUT_DIR = os.path.dirname(__file__)

# Font setup for Chinese characters
for font_name in ['Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'DejaVu Sans']:
    try:
        matplotlib.font_manager.findfont(font_name, fallback_to_default=False)
        plt.rcParams['font.sans-serif'] = [font_name, 'DejaVu Sans']
        break
    except Exception:
        continue
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# Drawio color palette (exact from reference)
# ============================================================
C_BLUE_BG     = '#dae8fc'
C_BLUE_STR    = '#6c8ebf'
C_ORANGE_BG   = '#ffe6cc'
C_ORANGE_STR  = '#d79b00'
C_GREEN_BG    = '#d5e8d4'
C_GREEN_STR   = '#82b366'
C_YELLOW_BG   = '#fff2cc'
C_YELLOW_STR  = '#d6b656'
C_RED_BG      = '#f8cecc'
C_RED_STR     = '#b85450'
C_PURPLE_BG   = '#e1d5e7'
C_PURPLE_STR  = '#9673a6'
C_DARK        = '#333333'
C_GRAY        = '#666666'
C_LIGHT_GRAY  = '#999999'

# ============================================================
# Helper functions — drawio-style
# ============================================================

def drawio_container(ax, x, y, w, h, label='', fontsize=11):
    """Sharp-corner dashed container like drawio rounded=0 dashPattern=12 12."""
    rect = Rectangle((x, y), w, h,
                      facecolor='none',
                      edgecolor=C_LIGHT_GRAY,
                      linewidth=1.5,
                      linestyle=(0, (6, 6)),  # dashPattern=12 12 at ~0.5pt/unit
                      zorder=1)
    ax.add_patch(rect)
    if label:
        ax.text(x + 0.3, y + h - 0.25, label, fontsize=fontsize,
                color=C_GRAY, fontweight='bold', fontstyle='italic',
                va='top', zorder=2)


def vert_side_label(ax, x, y, w, h, text, bg, stroke, fontsize=14):
    """Vertical text label on left side — like drawio textDirection=vertical-rl."""
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.08", facecolor=bg,
                          edgecolor=stroke, linewidth=1.8, zorder=3)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center',
            fontsize=fontsize, color='#333333', fontweight='bold',
            rotation=90, zorder=4)


def drawio_block(ax, x, y, w, h, text, bg, stroke,
                 fontsize=13, text_color='#333333', fontweight='bold',
                 round_pad=0.1, lw=1.8, alpha=1.0, align='center'):
    """Rounded rectangle block with multiline text — drawio style rounded=1."""
    r = FancyBboxPatch((x - w/2, y - h/2), w, h,
                       boxstyle=f"round,pad={round_pad}", facecolor=bg,
                       edgecolor=stroke, linewidth=lw, alpha=alpha, zorder=3)
    ax.add_patch(r)
    lines = text.split('\n')
    line_h = 0.35
    total_h = (len(lines) - 1) * line_h
    for i, line in enumerate(lines):
        is_sub = line.startswith('  ')
        fs = fontsize - 2 if is_sub else fontsize
        fw = 'normal' if is_sub else fontweight
        tc = text_color if not is_sub else '#555555'
        ax.text(x, y + total_h/2 - i * line_h, line.replace('  ', ''),
                ha=align, va='center', fontsize=fs,
                color=tc, fontweight=fw, zorder=4)


def drawio_arrow(ax, x1, y1, x2, y2, color=C_GRAY, lw=2.0):
    """Straight arrow."""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1), zorder=5,
                arrowprops=dict(arrowstyle='->', color=color, lw=lw))


def drawio_ortho_arrow(ax, x1, y1, x2, y2, color=C_GRAY, lw=2.0):
    """Right-angle arrow using waypoints — mimics drawio orthogonalEdgeStyle."""
    if abs(x1 - x2) < 0.01 or abs(y1 - y2) < 0.01:
        # Straight line
        drawio_arrow(ax, x1, y1, x2, y2, color=color, lw=lw)
        return
    mid_x = x2
    mid_y = y1
    ax.plot([x1, mid_x, x2], [y1, mid_y, y2], color=color, lw=lw, zorder=5)
    # Arrowhead at the end
    ax.annotate('', xy=(x2, y2), xytext=(mid_x, mid_y), zorder=5,
                arrowprops=dict(arrowstyle='->', color=color, lw=lw))


def edge_label(ax, x, y, text, fontsize=10, color=C_GRAY):
    """Label placed on/near an arrow — drawio edgeLabel style."""
    ax.text(x, y, text, fontsize=fontsize, color=color,
            ha='center', va='center', fontstyle='italic',
            bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                      edgecolor='none', alpha=0.85), zorder=6)


# ============================================================
# Main figure
# ============================================================
def main():
    fig, ax = plt.subplots(figsize=(18, 13))
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 14)
    ax.axis('off')
    ax.set_aspect('equal')

    # ===== UPPER SECTION: Physical System Layer =====
    drawio_container(ax, 0.4, 9.75, 14.5, 3.8,
                     label='Physical System Layer  /  物理系统层')

    vert_side_label(ax, 0.1, 10.05, 0.45, 3.15, '电池\n系统', C_BLUE_BG, C_BLUE_STR, fontsize=12)

    # Battery block
    drawio_block(ax, 3.8, 11.7, 3.6, 1.8,
                 'Li-ion Battery\n  NMC / Graphite',
                 C_BLUE_BG, C_BLUE_STR, fontsize=12)

    # Measurement block
    drawio_block(ax, 7.6, 11.7, 3.0, 1.8,
                 'Measurements\n  V_t , I , T',
                 C_ORANGE_BG, C_ORANGE_STR, fontsize=12)

    # Arrow: Battery → Measurements
    drawio_arrow(ax, 5.7, 11.7, 6.0, 11.7, color=C_GRAY, lw=2.0)

    # OCV-SOC block (below battery)
    drawio_block(ax, 3.8, 10.1, 3.2, 0.85,
                 'OCV-SOC Characterization',
                 C_BLUE_BG, C_BLUE_STR, fontsize=10)

    # Arrow: Battery → OCV-SOC (down)
    drawio_arrow(ax, 3.8, 10.8, 3.8, 10.55, color=C_BLUE_STR, lw=1.5)

    # ===== MIDDLE SECTION: Model Layer =====
    drawio_container(ax, 0.4, 4.85, 14.5, 4.55,
                     label='Model Layer  /  模型层')

    vert_side_label(ax, 0.1, 5.22, 0.45, 3.85, '模型\n层', C_GREEN_BG, C_GREEN_STR, fontsize=12)

    # Parameter Identification (left)
    drawio_block(ax, 3.0, 7.15, 3.6, 2.6,
                 'Offline Parameter ID\n'
                 '  Pulse-Relaxation Method\n'
                 '  (600 s pulse + 1800 s rest)\n'
                 '  →  τ_sd , K_sd',
                 C_PURPLE_BG, C_PURPLE_STR, fontsize=11)

    # Improved ECM (center-right)
    drawio_block(ax, 9.5, 7.15, 8.0, 2.6,
                 'Improved Equivalent Circuit Model\n'
                 '  State:  x = [SOC, V_1, V_sd]^T\n'
                 '  Output:  V_t = OCV(SOC) - V_1 - V_sd - I·R_0\n'
                 '  New Term:  G_sd(s) = K_sd / (τ_sd · s + 1)',
                 C_GREEN_BG, C_GREEN_STR, fontsize=12)

    # Arrow: Param ID → ECM
    drawio_arrow(ax, 4.9, 7.15, 5.9, 7.15, color=C_PURPLE_STR, lw=1.8)

    # Arrow: Param ID → Battery layer (initialize params feedback up)
    drawio_arrow(ax, 3.0, 8.45, 3.8, 9.35, color=C_PURPLE_STR, lw=1.5)
    edge_label(ax, 2.4, 8.95, 'Initialize\nParameters', fontsize=9, color=C_PURPLE_STR)

    # Arrow: Measurements → ECM (data flow down)
    drawio_arrow(ax, 7.6, 10.75, 7.6, 8.55, color=C_GRAY, lw=2.0)

    # ===== BOTTOM SECTION: Estimation Layer =====
    drawio_container(ax, 0.4, 0.4, 14.5, 4.1,
                     label='Estimation Layer  /  估计层')

    vert_side_label(ax, 0.1, 0.72, 0.45, 3.5, '估计\n层', C_YELLOW_BG, C_YELLOW_STR, fontsize=12)

    # UKF block (center)
    drawio_block(ax, 9.5, 2.6, 9.0, 2.6,
                 'Unscented Kalman Filter (UKF)\n'
                 '  (1) Sigma Points (2n+1)  →  (2) State Prediction\n'
                 '  (3) Measurement Update  →  (4) Kalman Gain  →  (5) State Correction\n'
                 '  Process Noise:  Q = diag(σ²_SOC, σ²_V1, σ²_Vsd)\n'
                 '  Measurement Noise:  R = σ²_v',
                 C_YELLOW_BG, C_YELLOW_STR, fontsize=11)

    # Arrow: ECM → UKF (main data flow down)
    drawio_arrow(ax, 9.5, 5.85, 9.5, 4.0, color='#e67e22', lw=2.8)

    # Innovation feedback loop (right side arc)
    ax.annotate('', xy=(14.8, 7.15), xytext=(15.2, 2.6), zorder=5,
                arrowprops=dict(arrowstyle='->', color=C_RED_STR, lw=2.0,
                                connectionstyle='arc3,rad=-0.35'))
    edge_label(ax, 16.0, 5.0, 'Voltage\nInnovation\nFeedback', fontsize=9, color=C_RED_STR)

    # ===== OUTPUT =====
    drawio_block(ax, 9.5, 0.35, 5.0, 0.9,
                 'SOC Estimate\n  with Error Bounds (±3σ)',
                 C_RED_BG, C_RED_STR, fontsize=11, text_color='#333333')

    # Arrow: UKF → Output
    drawio_arrow(ax, 9.5, 1.25, 9.5, 0.8, color=C_RED_STR, lw=2.2)

    # ===== Title =====
    fig.suptitle('Methodology Overview: Improved ECM + UKF Framework for SOC Estimation',
                 fontsize=17, fontweight='bold', y=0.99, color=C_DARK)

    plt.tight_layout(rect=[0, 0.02, 1, 0.97])
    path = os.path.join(OUT_DIR, 'fig_methodology.png')
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f'Saved: {path}')
    plt.close(fig)


if __name__ == '__main__':
    main()
