# graphics_utils.py
"""
Utility functions for graphical operations, including drawing primitives
and calculating positions for rendering.
"""
import math
from typing import Tuple, List

from PySide6 import QtCore, QtGui, QtWidgets # Assuming QPointF, QRectF are needed

# It's good practice to have a logger in new modules if you anticipate adding more complex functions later
import logging
logger = logging.getLogger(__name__)

def calculate_line_label_transform(
    p1: QtCore.QPointF,
    p2: QtCore.QPointF,
    text_rect: QtCore.QRectF,
    scene_bounding_rect: QtCore.QRectF,
    desired_gap_pixels: float = 3.0
) -> Tuple[QtCore.QPointF, float]:
    """
    Calculates the position and rotation for a text label associated with a line.

    Args:
        p1: Starting point of the line (scene coordinates).
        p2: Ending point of the line (scene coordinates).
        text_rect: The bounding rectangle of the text to be placed.
                   Its width and height are used for calculations.
        scene_bounding_rect: The bounding rectangle of the overall scene/image,
                             used to determine the center for perpendicular shifting.
        desired_gap_pixels: The desired gap between the line and the text label.

    Returns:
        A tuple containing:
            - QPointF: The calculated top-left position for the text_rect.
            - float: The calculated rotation angle in degrees for the text.
    """
    text_width = text_rect.width()
    text_height = text_rect.height()

    line_mid_x = (p1.x() + p2.x()) / 2.0
    line_mid_y = (p1.y() + p2.y()) / 2.0

    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    line_length = math.sqrt(dx * dx + dy * dy)

    if line_length < 1e-6:  # Handle zero-length or very short lines
        # Position text slightly offset from p1, no rotation
        return QtCore.QPointF(p1.x() + 2, p1.y() - text_height - 2), 0.0

    line_angle_rad = math.atan2(dy, dx)
    line_angle_deg = math.degrees(line_angle_rad)

    # Initial position: text centered with line midpoint, before rotation and shift
    initial_pos_x = line_mid_x - (text_width / 2.0)
    initial_pos_y = line_mid_y - (text_height / 2.0)

    # Rotation for the text to align with the line
    text_rotation_deg = line_angle_deg
    if text_rotation_deg > 90:
        text_rotation_deg -= 180
    elif text_rotation_deg < -90:
        text_rotation_deg += 180

    # Calculate perpendicular shift
    shift_magnitude = (text_height / 2.0) + desired_gap_pixels
    
    perp_dx = -dy / line_length
    perp_dy = dx / line_length

    img_center_x = scene_bounding_rect.center().x()
    img_center_y = scene_bounding_rect.center().y()

    test_pos1_x = line_mid_x + perp_dx * shift_magnitude
    test_pos1_y = line_mid_y + perp_dy * shift_magnitude
    dist_sq1 = (test_pos1_x - img_center_x)**2 + (test_pos1_y - img_center_y)**2
    
    test_pos2_x = line_mid_x - perp_dx * shift_magnitude
    test_pos2_y = line_mid_y - perp_dy * shift_magnitude
    dist_sq2 = (test_pos2_x - img_center_x)**2 + (test_pos2_y - img_center_y)**2

    final_shift_dx = perp_dx
    final_shift_dy = perp_dy
    if dist_sq2 < dist_sq1: 
        final_shift_dx = -perp_dx
        final_shift_dy = -perp_dy
        
    total_offset_x = final_shift_dx * shift_magnitude
    total_offset_y = final_shift_dy * shift_magnitude
    
    final_pos = QtCore.QPointF(initial_pos_x + total_offset_x, initial_pos_y + total_offset_y)

    return final_pos, text_rotation_deg

def draw_line_on_painter(painter: QtGui.QPainter,
                         p1: QtCore.QPointF,
                         p2: QtCore.QPointF,
                         pen: QtGui.QPen) -> None:
    """
    Draws a line on the given QPainter.
    Assumes the painter's pen will be set appropriately before calling for cosmetic effects.
    """
    painter.save()
    try:
        current_pen = QtGui.QPen(pen) # Work with a copy to ensure cosmetic is set
        current_pen.setCosmetic(True)
        painter.setPen(current_pen)
        painter.drawLine(p1, p2)
    finally:
        painter.restore()


def draw_marker_on_painter(painter: QtGui.QPainter,
                           pos: QtCore.QPointF,
                           size: float,
                           pen: QtGui.QPen) -> None:
    """
    Draws a cross marker (+) on the given QPainter.
    Assumes the painter's pen will be set appropriately before calling for cosmetic effects.
    """
    painter.save()
    try:
        current_pen = QtGui.QPen(pen) # Work with a copy
        current_pen.setCosmetic(True)
        painter.setPen(current_pen)
        
        r = size / 2.0
        x = pos.x()
        y = pos.y()
        
        painter.drawLine(QtCore.QPointF(x - r, y), QtCore.QPointF(x + r, y)) # Horizontal line
        painter.drawLine(QtCore.QPointF(x, y - r), QtCore.QPointF(x, y + r)) # Vertical line
    finally:
        painter.restore()

def create_line_qgraphicsitem(p1: QtCore.QPointF,
                              p2: QtCore.QPointF,
                              pen: QtGui.QPen,
                              z_value: float = 0.0) -> QtWidgets.QGraphicsLineItem:
    """
    Creates a QGraphicsLineItem.
    The pen should be cosmetic if pixel-width consistency is desired.
    """
    line_item = QtWidgets.QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
    
    # Work with a copy of the pen to ensure cosmetic setting without altering the original
    item_pen = QtGui.QPen(pen)
    item_pen.setCosmetic(True) # Ensure consistent line width regardless of view scale
    
    line_item.setPen(item_pen)
    line_item.setZValue(z_value)
    return line_item


def create_marker_qgraphicsitem(pos: QtCore.QPointF,
                                size: float,
                                pen: QtGui.QPen,
                                z_value: float = 0.0) -> QtWidgets.QGraphicsPathItem:
    """
    Creates a QGraphicsPathItem representing a cross marker (+).
    The pen should be cosmetic if pixel-width consistency is desired.
    """
    path = QtGui.QPainterPath()
    r = size / 2.0
    x = pos.x()
    y = pos.y()
    
    path.moveTo(x - r, y)
    path.lineTo(x + r, y)
    path.moveTo(x, y - r)
    path.lineTo(x, y + r)
    
    marker_item = QtWidgets.QGraphicsPathItem(path)
    
    item_pen = QtGui.QPen(pen) # Work with a copy
    item_pen.setCosmetic(True) # Ensure consistent marker line width
    
    marker_item.setPen(item_pen)
    marker_item.setZValue(z_value)
    return marker_item

def create_text_label_qgraphicsitem(text: str,
                                    line_p1: QtCore.QPointF,
                                    line_p2: QtCore.QPointF,
                                    font_size: int,
                                    color: QtGui.QColor,
                                    scene_context_rect: QtCore.QRectF,
                                    z_value: float = 0.0) -> QtWidgets.QGraphicsSimpleTextItem:
    """
    Creates a QGraphicsSimpleTextItem for a line label, positioned and rotated.

    Args:
        text: The string content of the label.
        line_p1: The first point of the line the label is associated with.
        line_p2: The second point of the line the label is associated with.
        font_size: The point size of the font for the label.
        color: The QColor for the text.
        scene_context_rect: The bounding rectangle of the scene, used for positioning context.
        z_value: The Z-value for stacking order in the scene.

    Returns:
        A configured QGraphicsSimpleTextItem.
    """
    text_item = QtWidgets.QGraphicsSimpleTextItem(text)
    
    current_font = text_item.font() # Get default font from the item
    current_font.setPointSize(font_size)
    text_item.setFont(current_font)
    
    if isinstance(color, QtGui.QColor) and color.isValid():
        text_item.setBrush(QtGui.QBrush(color))
    else:
        logger.warning(f"Invalid color ('{color}') provided for text label. Defaulting to black.")
        text_item.setBrush(QtGui.QBrush(QtGui.QColor("black")))

    # Calculate position and rotation using the existing utility function
    # text_item.boundingRect() gives the bounding rectangle of the text itself
    text_pos, text_rot_deg = calculate_line_label_transform(
        line_p1,
        line_p2,
        text_item.boundingRect(),
        scene_context_rect
    )
    
    text_item.setPos(text_pos)
    
    # Set transform origin to the center of the text item for proper rotation
    text_center_x = text_item.boundingRect().width() / 2.0
    text_center_y = text_item.boundingRect().height() / 2.0
    text_item.setTransformOriginPoint(text_center_x, text_center_y)
    text_item.setRotation(text_rot_deg)
    
    text_item.setZValue(z_value)
    
    return text_item

def create_defined_scale_display_items(
    p1x: float, p1y: float, p2x: float, p2y: float,
    length_text: str,
    line_pen: QtGui.QPen,  # Pen for the main line and ticks/dots
    text_color: QtGui.QColor,
    font_size: int,
    show_ticks: bool,
    tick_length_factor: float,  # As a multiple of pen_width for ticks
    scene_context_rect: QtCore.QRectF,
    z_value_line: float = 11.5, # Base Z for line, ticks slightly above/same
    z_value_text: float = 12.0  # Text on top
) -> List[QtWidgets.QGraphicsItem]:
    """
    Creates a list of QGraphicsItems representing the defined scale line,
    its ticks (or dots), and its length label.
    """
    items: List[QtWidgets.QGraphicsItem] = []
    p1 = QtCore.QPointF(p1x, p1y)
    p2 = QtCore.QPointF(p2x, p2y)

    # Main line item
    main_line_item = create_line_qgraphicsitem(p1, p2, line_pen, z_value=z_value_line)
    items.append(main_line_item)

    # Ticks or Dots
    # Pen width for tick length calculation (use a copy to ensure it's cosmetic for actual drawing)
    cosmetic_line_pen = QtGui.QPen(line_pen)
    cosmetic_line_pen.setCosmetic(True)
    actual_pen_width = cosmetic_line_pen.widthF()
    if actual_pen_width <= 0: # Ensure a minimum visible width for calculations if pen width is 0
        actual_pen_width = 1.0

    tick_total_length = actual_pen_width * tick_length_factor
    half_tick_length = tick_total_length / 2.0

    dx = p2x - p1x
    dy = p2y - p1y
    line_length_for_norm = math.sqrt(dx*dx + dy*dy)

    if show_ticks and tick_total_length > 0:
        if line_length_for_norm > 1e-6:
            norm_perp_dx = -dy / line_length_for_norm
            norm_perp_dy = dx / line_length_for_norm

            for pt in [p1, p2]:
                tick_p1 = QtCore.QPointF(pt.x() + norm_perp_dx * half_tick_length, 
                                         pt.y() + norm_perp_dy * half_tick_length)
                tick_p2 = QtCore.QPointF(pt.x() - norm_perp_dx * half_tick_length, 
                                         pt.y() - norm_perp_dy * half_tick_length)
                tick_item = create_line_qgraphicsitem(tick_p1, tick_p2, line_pen, z_value=z_value_line + 0.1)
                items.append(tick_item)
    elif not show_ticks:  # Draw dots if ticks are disabled
        marker_radius = max(1.0, actual_pen_width / 2.0)
        dot_pen = QtGui.QPen(line_pen.color(), 0.5) # Thin border for dot
        dot_pen.setCosmetic(True)
        dot_brush = QtGui.QBrush(line_pen.color())

        for pt in [p1, p2]:
            dot_marker = QtWidgets.QGraphicsEllipseItem(pt.x() - marker_radius, pt.y() - marker_radius,
                                                        2 * marker_radius, 2 * marker_radius)
            dot_marker.setPen(dot_pen)
            dot_marker.setBrush(dot_brush)
            dot_marker.setZValue(z_value_line + 0.1)
            items.append(dot_marker)

    # Text label item
    text_item = create_text_label_qgraphicsitem(
        text=length_text,
        line_p1=p1,
        line_p2=p2,
        font_size=font_size,
        color=text_color,
        scene_context_rect=scene_context_rect,
        z_value=z_value_text
    )
    items.append(text_item)
    
    logger.debug(f"Created {len(items)} QGraphicsItems for defined scale display.")
    return items


def draw_defined_scale_display_on_painter(
    painter: QtGui.QPainter,
    p1x: float, p1y: float, p2x: float, p2y: float,
    length_text: str,
    line_pen: QtGui.QPen,  # Pen for the main line and ticks/dots
    text_color: QtGui.QColor,
    font_size: int,
    show_ticks: bool,
    tick_length_factor: float, # As a multiple of pen_width
    scene_context_rect: QtCore.QRectF
) -> None:
    """
    Draws the defined scale line, its ticks (or dots), and its length label
    directly onto a QPainter.
    """
    p1 = QtCore.QPointF(p1x, p1y)
    p2 = QtCore.QPointF(p2x, p2y)

    # Draw Main line
    draw_line_on_painter(painter, p1, p2, line_pen)

    # Draw Ticks or Dots
    cosmetic_line_pen = QtGui.QPen(line_pen)
    cosmetic_line_pen.setCosmetic(True)
    actual_pen_width = cosmetic_line_pen.widthF()
    if actual_pen_width <= 0:
        actual_pen_width = 1.0
        
    tick_total_length = actual_pen_width * tick_length_factor
    half_tick_length = tick_total_length / 2.0

    dx = p2x - p1x
    dy = p2y - p1y
    line_length_for_norm = math.sqrt(dx*dx + dy*dy)

    if show_ticks and tick_total_length > 0:
        if line_length_for_norm > 1e-6:
            norm_perp_dx = -dy / line_length_for_norm
            norm_perp_dy = dx / line_length_for_norm

            for pt in [p1, p2]:
                tick_p1 = QtCore.QPointF(pt.x() + norm_perp_dx * half_tick_length, 
                                         pt.y() + norm_perp_dy * half_tick_length)
                tick_p2 = QtCore.QPointF(pt.x() - norm_perp_dx * half_tick_length, 
                                         pt.y() - norm_perp_dy * half_tick_length)
                draw_line_on_painter(painter, tick_p1, tick_p2, line_pen)
    elif not show_ticks:
        painter.save()
        painter.setBrush(QtGui.QBrush(line_pen.color()))
        dot_pen = QtGui.QPen(line_pen.color(), 0.5)
        dot_pen.setCosmetic(True)
        painter.setPen(dot_pen)
        marker_radius = max(1.0, actual_pen_width / 2.0)
        for pt in [p1, p2]:
            painter.drawEllipse(QtCore.QRectF(pt.x() - marker_radius, pt.y() - marker_radius,
                                               2 * marker_radius, 2 * marker_radius))
        painter.restore()

    # Draw Text label
    current_export_font = QtGui.QFont()
    current_export_font.setPointSize(font_size)
    
    # Note: draw_text_label_for_line_on_painter is not defined yet in our sequence.
    # We'll use the direct logic here for now, similar to what was in ExportHandler.
    # This can be refactored later if draw_text_label_for_line_on_painter is created.
    
    font_metrics = QtGui.QFontMetrics(current_export_font)
    text_bounding_rect_local = font_metrics.boundingRect(length_text)
                
    text_pos_scene, text_rot_deg = calculate_line_label_transform(
        p1,
        p2,
        text_bounding_rect_local,
        scene_context_rect 
    )

    painter.save()
    try:
        painter.translate(text_pos_scene.x() + text_bounding_rect_local.width() / 2.0,
                          text_pos_scene.y() + text_bounding_rect_local.height() / 2.0)
        painter.rotate(text_rot_deg)
        
        painter.setFont(current_export_font)
        painter.setPen(text_color) # text_color is already a QColor
        
        painter.drawText(QtCore.QPointF(-text_bounding_rect_local.width() / 2.0,
                                         -text_bounding_rect_local.height() / 2.0 + font_metrics.ascent()),
                         length_text)
    finally:
        painter.restore()
    
    logger.debug("Drew defined scale display directly on painter.")