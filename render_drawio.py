"""
Render draw.io XML to high-resolution PNG using matplotlib.
Reads fig_methodology.drawio.xml and outputs fig_methodology.png.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch, Arc
import matplotlib.patches as mpatches
import numpy as np
import os
import re
import html
import xml.etree.ElementTree as ET

OUT_DIR = os.path.dirname(__file__)

# Font setup
for font_name in ['Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'DejaVu Sans']:
    try:
        matplotlib.font_manager.findfont(font_name, fallback_to_default=False)
        plt.rcParams['font.sans-serif'] = [font_name, 'DejaVu Sans']
        break
    except Exception:
        continue
plt.rcParams['axes.unicode_minus'] = False


def parse_html_text(html_text):
    """Extract plain text lines from draw.io HTML-formatted cell value."""
    if not html_text:
        return ['']
    # Decode HTML entities
    text = html.unescape(html_text)
    # Remove HTML tags but keep <br> as newline
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    # Remove extra whitespace
    lines = [l.strip() for l in text.split('\n')]
    return lines if lines else ['']


def parse_style(style_str):
    """Parse draw.io style string into dict."""
    if not style_str:
        return {}
    props = {}
    for part in style_str.split(';'):
        if '=' in part:
            k, v = part.split('=', 1)
            props[k.strip()] = v.strip()
        elif part.strip():
            props[part.strip()] = True
    return props


def hex_to_rgb(hex_color):
    """Convert #rrggbb or #rgb to (r,g,b) 0-1."""
    c = hex_color.lstrip('#')
    if len(c) == 3:
        c = c[0]*2 + c[1]*2 + c[2]*2
    return tuple(int(c[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def render_drawio(xml_path, png_path, dpi=200):
    """Render a draw.io XML file to PNG."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    ns = {'mx': ''}  # no namespace in our file

    # Find the diagram and mxGraphModel
    model = root.find('.//mxGraphModel')
    if model is None:
        raise ValueError("No mxGraphModel found")

    page_w = int(model.get('pageWidth', 1200))
    page_h = int(model.get('pageHeight', 1100))

    # Collect cells
    cells = {}
    vertices = []
    edges = []
    root_cell = model.find('root')
    for cell in root_cell.findall('mxCell'):
        cid = cell.get('id')
        cells[cid] = cell
        if cell.get('vertex') == '1':
            vertices.append(cell)
        elif cell.get('edge') == '1':
            edges.append(cell)

    # Map parent relationships (for reference only)
    # parent_id in cells is used for relative positioning

    # Setup figure — map drawio coords to matplotlib (flip Y)
    fig, ax = plt.subplots(figsize=(page_w/100, page_h/100))
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.invert_yaxis()
    ax.axis('off')
    ax.set_aspect('equal')

    # Draw containers first (non-rounded rectangles, dashed)
    for cell in vertices:
        geom = cell.find('mxGeometry')
        if geom is None:
            continue
        x = float(geom.get('x', 0))
        y = float(geom.get('y', 0))
        w = float(geom.get('width', 100))
        h = float(geom.get('height', 100))
        style = parse_style(cell.get('style', ''))
        value = cell.get('value', '')

        rounded = style.get('rounded', '0') == '1'
        dashed = style.get('dashed', '0') == '1'
        fill_color = style.get('fillColor', 'none')
        stroke_color = style.get('strokeColor', '#000000')

        # Skip text-only elements (render later)
        if not style.get('whiteSpace') and style.get('text') == True:
            # Pure text element
            lines = parse_html_text(value)
            font_size = 12
            if value and 'font-size' in value:
                m = re.search(r'font-size:\s*(\d+)px', value)
                if m:
                    font_size = int(m.group(1))
            for i, line in enumerate(lines):
                ax.text(x + 5, y + 5 + i * font_size * 1.3, line,
                        fontsize=font_size, color='#333333', zorder=5)
            continue

        # Draw shape
        if w == 0 or h == 0:
            continue

        fc = hex_to_rgb(fill_color) if fill_color != 'none' else (1, 1, 1, 0)
        ec = hex_to_rgb(stroke_color)
        lw = float(style.get('strokeWidth', 1.5))

        if dashed:
            rect = Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec,
                             linewidth=lw, linestyle=(0, (6, 6)), zorder=1)
        elif rounded:
            rect = FancyBboxPatch((x, y), w, h,
                                  boxstyle="round,pad=0.15", facecolor=fc,
                                  edgecolor=ec, linewidth=lw, zorder=3)
        else:
            rect = Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec,
                             linewidth=lw, zorder=1)

        ax.add_patch(rect)

        # Draw text inside shape
        if value:
            lines = parse_html_text(value)
            if lines and lines[0]:
                # Check for vertical text direction
                is_vertical = style.get('textDirection') == 'vertical-rl'

                # Extract font size from HTML
                font_size = 13
                if 'font-size' in value:
                    sizes = re.findall(r'font-size:\s*(\d+)px', value)
                    if sizes:
                        font_size = max(int(s) for s in sizes)

                cx, cy = x + w/2, y + h/2
                if is_vertical:
                    text_str = ''.join(lines)
                    ax.text(cx, cy, text_str, ha='center', va='center',
                            fontsize=font_size, fontweight='bold',
                            rotation=90, zorder=4)
                else:
                    # Multi-line centered text
                    line_h = font_size * 0.045  # approximate in data coords
                    total_h = (len(lines) - 1) * line_h
                    for i, line in enumerate(lines):
                        is_bold = '<b>' in value
                        fs = font_size - 2 if line.startswith('  ') else font_size
                        ax.text(cx, cy + total_h/2 - i * line_h,
                                line.replace('  ', ''),
                                ha='center', va='center', fontsize=fs,
                                color='#333333',
                                fontweight='bold' if is_bold else 'normal',
                                zorder=4)

    # Draw edges
    for cell in edges:
        style = parse_style(cell.get('style', ''))
        source_id = cell.get('source')
        target_id = cell.get('target')
        value = cell.get('value', '')

        if source_id not in cells or target_id not in cells:
            continue

        src_geom = cells[source_id].find('mxGeometry')
        tgt_geom = cells[target_id].find('mxGeometry')
        if src_geom is None or tgt_geom is None:
            continue

        sx = float(src_geom.get('x', 0))
        sy = float(src_geom.get('y', 0))
        sw = float(src_geom.get('width', 100))
        sh = float(src_geom.get('height', 100))
        tx = float(tgt_geom.get('x', 0))
        ty = float(tgt_geom.get('y', 0))
        tw = float(tgt_geom.get('width', 100))
        th = float(tgt_geom.get('height', 100))

        # Source center, target center
        scx, scy = sx + sw/2, sy + sh/2
        tcx, tcy = tx + tw/2, ty + th/2

        # Collect waypoints
        waypoints = []
        geom = cell.find('mxGeometry')
        if geom is not None:
            points_arr = geom.find('Array')
            if points_arr is not None:
                for pt in points_arr.findall('mxPoint'):
                    px = float(pt.get('x', 0))
                    py = float(pt.get('y', 0))
                    waypoints.append((px, py))

        stroke_color = style.get('strokeColor', '#666666')
        ec = hex_to_rgb(stroke_color)
        lw = float(style.get('strokeWidth', 2))

        # Build path with waypoints
        path_x = [scx]
        path_y = [scy]
        for wx, wy in waypoints:
            path_x.append(wx)
            path_y.append(wy)
        path_x.append(tcx)
        path_y.append(tcy)

        ax.plot(path_x, path_y, color=ec, linewidth=lw, zorder=2)

        # Arrowhead at the last segment
        if len(path_x) >= 2:
            ax.annotate('', xy=(path_x[-1], path_y[-1]),
                        xytext=(path_x[-2], path_y[-2]),
                        zorder=5,
                        arrowprops=dict(arrowstyle='->', color=ec, lw=lw))

        # Edge label
        if value:
            label_lines = parse_html_text(value)
            if label_lines:
                label_size = 10
                if 'font-size' in value:
                    m = re.search(r'font-size:\s*(\d+)px', value)
                    if m:
                        label_size = int(m.group(1))

                # Place label near midpoint of path
                mid_idx = len(path_x) // 2
                lx, ly = path_x[mid_idx], path_y[mid_idx]
                label_text = '\n'.join(label_lines)
                ax.text(lx + 5, ly - 5, label_text, fontsize=label_size,
                        color='#666666', ha='center', va='center',
                        fontstyle='italic',
                        bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                                  edgecolor='none', alpha=0.85), zorder=6)

    plt.tight_layout(pad=0)
    fig.savefig(png_path, dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f'Saved: {png_path}')
    return png_path


if __name__ == '__main__':
    xml_path = os.path.join(OUT_DIR, 'fig_methodology.drawio.xml')
    png_path = os.path.join(OUT_DIR, 'fig_methodology.png')
    render_drawio(xml_path, png_path, dpi=200)
