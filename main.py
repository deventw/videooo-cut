"""
Main entry point for the videooo-cut GUI application.
Video editing tool with import, preview, rotation, crop, and export features.
"""
import sys
import cv2
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
    QPushButton, QLabel, QFileDialog, QSlider, QSpinBox, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QMessageBox,
    QCheckBox, QProgressDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QCursor
from translations import tr, get_language_name


class VideoPreviewWidget(QLabel):
    """Widget for displaying video frames with smooth crop selection."""
    
    crop_changed = pyqtSignal(QRect)
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 2px solid #333; background-color: #000;")
        self.setText("No video loaded")
        
        self.current_frame = None
        self.base_pixmap = None  # Cached pixmap without crop overlay
        self.crop_rect = None
        self.crop_rect_widget = None  # Crop rect in widget coordinates
        self.shadow_crop_rects = []  # List of shadow crop rectangles (additional copies)
        self.shadow_crop_rects_widget = []  # Widget coordinates for shadow crops
        self.drawing = False
        self.adjusting = False  # True when fine-tuning existing crop
        self.adjust_mode = None  # 'move', 'resize_tl', 'resize_tr', 'resize_bl', 'resize_br', 'resize_t', 'resize_b', 'resize_l', 'resize_r'
        self.start_point = None
        self.end_point = None
        self.start_point_widget = None
        self.end_point_widget = None
        self.original_crop_rect = None  # Original crop rect when starting adjustment
        self.original_crop_rect_widget = None
        
        # Coordinate transformation cache
        self.frame_to_widget_scale_x = 1.0
        self.frame_to_widget_scale_y = 1.0
        self.widget_offset_x = 0
        self.widget_offset_y = 0
        
        # Handle size for fine-tuning
        self.handle_size = 10
        
        # Aspect ratio and size constraints
        self.lock_aspect_ratio = False
        self.aspect_ratio = None  # (width, height) tuple or None for free
        self.lock_size = False
        self.locked_size = None  # (width, height) tuple or None
        
        # Shadow cropping
        self.shadow_count = 1  # Number of segments (default 1)
        
    def set_frame(self, frame):
        """Set the current frame to display."""
        if frame is None:
            return
            
        self.current_frame = frame.copy()
        self.update_base_pixmap()
        self.update_display()
    
    def update_base_pixmap(self):
        """Update the cached base pixmap (without crop overlay)."""
        if self.current_frame is None:
            return
        
        # Convert to QPixmap
        height, width, channel = self.current_frame.shape
        bytes_per_line = 3 * width
        q_image = QImage(
            self.current_frame.data, 
            width, 
            height, 
            bytes_per_line, 
            QImage.Format.Format_RGB888
        ).rgbSwapped()
        
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale to fit widget while maintaining aspect ratio
        self.base_pixmap = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Cache transformation parameters
        widget_rect = self.rect()
        pixmap_rect = self.base_pixmap.rect()
        
        self.frame_to_widget_scale_x = pixmap_rect.width() / width
        self.frame_to_widget_scale_y = pixmap_rect.height() / height
        self.widget_offset_x = (widget_rect.width() - pixmap_rect.width()) / 2
        self.widget_offset_y = (widget_rect.height() - pixmap_rect.height()) / 2
    
    def widget_to_frame_coords(self, widget_point):
        """Convert widget coordinates to frame coordinates."""
        if self.current_frame is None:
            return None
        
        x = (widget_point.x() - self.widget_offset_x) / self.frame_to_widget_scale_x
        y = (widget_point.y() - self.widget_offset_y) / self.frame_to_widget_scale_y
        
        frame_height, frame_width = self.current_frame.shape[:2]
        x = max(0, min(int(x), frame_width))
        y = max(0, min(int(y), frame_height))
        
        return QPoint(x, y)
    
    def frame_to_widget_coords(self, frame_point):
        """Convert frame coordinates to widget coordinates."""
        x = frame_point.x() * self.frame_to_widget_scale_x + self.widget_offset_x
        y = frame_point.y() * self.frame_to_widget_scale_y + self.widget_offset_y
        return QPoint(int(x), int(y))
    
    def get_crop_handle_at(self, point):
        """Determine which part of the crop rectangle is at the given point."""
        if not self.crop_rect_widget:
            return None
        
        rect = self.crop_rect_widget
        handle_size = self.handle_size
        
        # Check corners (priority - smaller area)
        if abs(point.x() - rect.left()) <= handle_size and abs(point.y() - rect.top()) <= handle_size:
            return 'resize_tl'
        if abs(point.x() - rect.right()) <= handle_size and abs(point.y() - rect.top()) <= handle_size:
            return 'resize_tr'
        if abs(point.x() - rect.left()) <= handle_size and abs(point.y() - rect.bottom()) <= handle_size:
            return 'resize_bl'
        if abs(point.x() - rect.right()) <= handle_size and abs(point.y() - rect.bottom()) <= handle_size:
            return 'resize_br'
        
        # Check edges
        if abs(point.y() - rect.top()) <= handle_size and rect.left() <= point.x() <= rect.right():
            return 'resize_t'
        if abs(point.y() - rect.bottom()) <= handle_size and rect.left() <= point.x() <= rect.right():
            return 'resize_b'
        if abs(point.x() - rect.left()) <= handle_size and rect.top() <= point.y() <= rect.bottom():
            return 'resize_l'
        if abs(point.x() - rect.right()) <= handle_size and rect.top() <= point.y() <= rect.bottom():
            return 'resize_r'
        
        # Check if inside (for moving)
        if rect.contains(point):
            return 'move'
        
        return None
    
    def get_cursor_for_handle(self, handle):
        """Get the appropriate cursor for the handle type."""
        cursor_map = {
            'resize_tl': Qt.CursorShape.SizeFDiagCursor,
            'resize_tr': Qt.CursorShape.SizeBDiagCursor,
            'resize_bl': Qt.CursorShape.SizeBDiagCursor,
            'resize_br': Qt.CursorShape.SizeFDiagCursor,
            'resize_t': Qt.CursorShape.SizeVerCursor,
            'resize_b': Qt.CursorShape.SizeVerCursor,
            'resize_l': Qt.CursorShape.SizeHorCursor,
            'resize_r': Qt.CursorShape.SizeHorCursor,
            'move': Qt.CursorShape.SizeAllCursor,
        }
        return cursor_map.get(handle, Qt.CursorShape.ArrowCursor)
    
    def paintEvent(self, event):
        """Custom paint event to draw crop overlay smoothly."""
        super().paintEvent(event)
        
        if self.base_pixmap is None:
            return
        
        # Draw base pixmap
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pixmap_rect = self.base_pixmap.rect()
        pixmap_rect.moveCenter(self.rect().center())
        painter.drawPixmap(pixmap_rect, self.base_pixmap)
        
        # Draw shadow crop rectangles (lighter color, no handles)
        for shadow_rect in self.shadow_crop_rects_widget:
            pen = QPen(QColor(0, 200, 0), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 200, 0, 20))  # Lighter semi-transparent fill
            painter.drawRect(shadow_rect)
        
        # Draw main crop rectangle overlay (much faster than redrawing entire frame)
        if self.crop_rect_widget:
            pen = QPen(QColor(0, 255, 0), 2)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 255, 0, 30))  # Semi-transparent fill
            painter.drawRect(self.crop_rect_widget)
            
            # Draw corner handles
            handle_size = self.handle_size
            corners = [
                self.crop_rect_widget.topLeft(),
                self.crop_rect_widget.topRight(),
                self.crop_rect_widget.bottomLeft(),
                self.crop_rect_widget.bottomRight()
            ]
            for corner in corners:
                painter.fillRect(
                    corner.x() - handle_size // 2,
                    corner.y() - handle_size // 2,
                    handle_size,
                    handle_size,
                    QColor(0, 255, 0)
                )
            
            # Draw edge handles (smaller)
            edge_handle_size = 6
            # Top edge
            top_mid = QPoint((self.crop_rect_widget.left() + self.crop_rect_widget.right()) // 2, self.crop_rect_widget.top())
            painter.fillRect(
                top_mid.x() - edge_handle_size // 2,
                top_mid.y() - edge_handle_size // 2,
                edge_handle_size,
                edge_handle_size,
                QColor(0, 255, 0)
            )
            # Bottom edge
            bottom_mid = QPoint((self.crop_rect_widget.left() + self.crop_rect_widget.right()) // 2, self.crop_rect_widget.bottom())
            painter.fillRect(
                bottom_mid.x() - edge_handle_size // 2,
                bottom_mid.y() - edge_handle_size // 2,
                edge_handle_size,
                edge_handle_size,
                QColor(0, 255, 0)
            )
            # Left edge
            left_mid = QPoint(self.crop_rect_widget.left(), (self.crop_rect_widget.top() + self.crop_rect_widget.bottom()) // 2)
            painter.fillRect(
                left_mid.x() - edge_handle_size // 2,
                left_mid.y() - edge_handle_size // 2,
                edge_handle_size,
                edge_handle_size,
                QColor(0, 255, 0)
            )
            # Right edge
            right_mid = QPoint(self.crop_rect_widget.right(), (self.crop_rect_widget.top() + self.crop_rect_widget.bottom()) // 2)
            painter.fillRect(
                right_mid.x() - edge_handle_size // 2,
                right_mid.y() - edge_handle_size // 2,
                edge_handle_size,
                edge_handle_size,
                QColor(0, 255, 0)
            )
    
    def update_display(self):
        """Update the display (triggers repaint)."""
        self.update()
    
    def mousePressEvent(self, event):
        """Handle mouse press for crop selection or fine-tuning."""
        if self.current_frame is None:
            return
            
        if event.button() == Qt.MouseButton.LeftButton:
            mouse_pos = event.position().toPoint()
            
            # Check if clicking on existing crop rectangle
            handle = self.get_crop_handle_at(mouse_pos) if self.crop_rect_widget else None
            
            if handle:
                # Fine-tuning existing crop
                self.adjusting = True
                self.adjust_mode = handle
                self.original_crop_rect = QRect(self.crop_rect) if self.crop_rect else None
                self.original_crop_rect_widget = QRect(self.crop_rect_widget) if self.crop_rect_widget else None
                self.start_point_widget = mouse_pos
                self.end_point_widget = mouse_pos
            else:
                # Creating new crop selection
                self.drawing = True
                self.adjusting = False
                self.adjust_mode = None
                frame_point = self.widget_to_frame_coords(mouse_pos)
                if frame_point:
                    self.start_point = frame_point
                    self.end_point = frame_point
                    self.start_point_widget = mouse_pos
                    self.end_point_widget = mouse_pos
                    self.update_crop_rect()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for crop selection or fine-tuning - smooth and responsive."""
        mouse_pos = event.position().toPoint()
        
        # Update cursor based on hover position
        if not self.drawing and not self.adjusting:
            handle = self.get_crop_handle_at(mouse_pos) if self.crop_rect_widget else None
            if handle:
                self.setCursor(self.get_cursor_for_handle(handle))
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        
        if self.adjusting and self.current_frame is not None and self.original_crop_rect_widget:
            # Fine-tuning existing crop
            self.adjust_crop_rect(mouse_pos)
        elif self.drawing and self.current_frame is not None:
            # Creating new crop selection
            # Clamp widget coordinates to pixmap area
            if self.base_pixmap:
                pixmap_rect = self.base_pixmap.rect()
                pixmap_rect.moveCenter(self.rect().center())
                mouse_pos.setX(max(pixmap_rect.left(), min(mouse_pos.x(), pixmap_rect.right())))
                mouse_pos.setY(max(pixmap_rect.top(), min(mouse_pos.y(), pixmap_rect.bottom())))
            
            # If aspect ratio is set, maintain it during dragging
            if self.lock_aspect_ratio and self.aspect_ratio and self.start_point_widget:
                # Calculate the constrained end point based on aspect ratio
                delta_x = mouse_pos.x() - self.start_point_widget.x()
                delta_y = mouse_pos.y() - self.start_point_widget.y()
                
                target_ratio = self.aspect_ratio[0] / self.aspect_ratio[1]
                
                # Use the larger delta to determine size, then adjust the other dimension
                if abs(delta_x) > abs(delta_y):
                    # Width-driven
                    constrained_width = abs(delta_x)
                    constrained_height = int(constrained_width / target_ratio)
                    if delta_x < 0:
                        mouse_pos.setX(self.start_point_widget.x() - constrained_width)
                    else:
                        mouse_pos.setX(self.start_point_widget.x() + constrained_width)
                    if delta_y < 0:
                        mouse_pos.setY(self.start_point_widget.y() - constrained_height)
                    else:
                        mouse_pos.setY(self.start_point_widget.y() + constrained_height)
                else:
                    # Height-driven
                    constrained_height = abs(delta_y)
                    constrained_width = int(constrained_height * target_ratio)
                    if delta_y < 0:
                        mouse_pos.setY(self.start_point_widget.y() - constrained_height)
                    else:
                        mouse_pos.setY(self.start_point_widget.y() + constrained_height)
                    if delta_x < 0:
                        mouse_pos.setX(self.start_point_widget.x() - constrained_width)
                    else:
                        mouse_pos.setX(self.start_point_widget.x() + constrained_width)
                
                # Re-clamp to pixmap bounds
                if self.base_pixmap:
                    mouse_pos.setX(max(pixmap_rect.left(), min(mouse_pos.x(), pixmap_rect.right())))
                    mouse_pos.setY(max(pixmap_rect.top(), min(mouse_pos.y(), pixmap_rect.bottom())))
            
            frame_point = self.widget_to_frame_coords(mouse_pos)
            if frame_point:
                self.end_point = frame_point
                self.end_point_widget = mouse_pos
                self.update_crop_rect()
                # Just trigger repaint - much faster!
                self.update()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release for crop selection or fine-tuning."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.adjusting:
                self.adjusting = False
                self.adjust_mode = None
                self.original_crop_rect = None
                self.original_crop_rect_widget = None
            else:
                self.drawing = False
                if self.start_point and self.end_point:
                    self.update_crop_rect()
            self.update_display()
    
    def adjust_crop_rect(self, mouse_pos_widget):
        """Adjust existing crop rectangle based on drag mode."""
        if not self.original_crop_rect_widget or self.current_frame is None:
            return
        
        # Clamp mouse to pixmap bounds
        if self.base_pixmap:
            pixmap_rect = self.base_pixmap.rect()
            pixmap_rect.moveCenter(self.rect().center())
            mouse_pos_widget.setX(max(pixmap_rect.left(), min(mouse_pos_widget.x(), pixmap_rect.right())))
            mouse_pos_widget.setY(max(pixmap_rect.top(), min(mouse_pos_widget.y(), pixmap_rect.bottom())))
        
        delta_x = mouse_pos_widget.x() - self.start_point_widget.x()
        delta_y = mouse_pos_widget.y() - self.start_point_widget.y()
        
        orig = self.original_crop_rect_widget
        frame_height, frame_width = self.current_frame.shape[:2]
        
        # If aspect ratio is locked, maintain it during resize
        if self.lock_aspect_ratio and self.aspect_ratio and self.adjust_mode != 'move':
            target_ratio = self.aspect_ratio[0] / self.aspect_ratio[1]
            orig_ratio = orig.width() / orig.height() if orig.height() > 0 else 0
            
            # Calculate which dimension to use as primary based on adjust mode
            if self.adjust_mode in ['resize_tl', 'resize_tr', 'resize_bl', 'resize_br']:
                # Corner resize - use the larger delta
                if abs(delta_x) > abs(delta_y):
                    # Width-driven
                    new_width = orig.width() + delta_x if self.adjust_mode in ['resize_tr', 'resize_br'] else orig.width() - delta_x
                    new_height = int(new_width / target_ratio)
                    # Adjust delta_y to match
                    if self.adjust_mode in ['resize_tl', 'resize_tr']:
                        delta_y = orig.height() - new_height
                    else:
                        delta_y = new_height - orig.height()
                else:
                    # Height-driven
                    new_height = orig.height() - delta_y if self.adjust_mode in ['resize_tl', 'resize_tr'] else orig.height() + delta_y
                    new_width = int(new_height * target_ratio)
                    # Adjust delta_x to match
                    if self.adjust_mode in ['resize_tl', 'resize_bl']:
                        delta_x = orig.width() - new_width
                    else:
                        delta_x = new_width - orig.width()
            elif self.adjust_mode in ['resize_t', 'resize_b']:
                # Vertical resize - adjust width to maintain ratio
                new_height = orig.height() - delta_y if self.adjust_mode == 'resize_t' else orig.height() + delta_y
                new_width = int(new_height * target_ratio)
                delta_x = new_width - orig.width()
            elif self.adjust_mode in ['resize_l', 'resize_r']:
                # Horizontal resize - adjust height to maintain ratio
                new_width = orig.width() - delta_x if self.adjust_mode == 'resize_l' else orig.width() + delta_x
                new_height = int(new_width / target_ratio)
                delta_y = new_height - orig.height()
        
        # Calculate new widget rect based on adjust mode
        if self.adjust_mode == 'move':
            # For move, maintain size and constrain position
            new_x = orig.x() + delta_x
            new_y = orig.y() + delta_y
            
            # Constrain position but maintain size
            if self.base_pixmap:
                pixmap_rect = self.base_pixmap.rect()
                pixmap_rect.moveCenter(self.rect().center())
                
                # Don't allow moving outside bounds
                new_x = max(pixmap_rect.left(), min(new_x, pixmap_rect.right() - orig.width()))
                new_y = max(pixmap_rect.top(), min(new_y, pixmap_rect.bottom() - orig.height()))
            
            new_rect_widget = QRect(
                new_x,
                new_y,
                orig.width(),
                orig.height()
            )
        elif self.adjust_mode == 'resize_tl':
            new_rect_widget = QRect(
                orig.x() + delta_x,
                orig.y() + delta_y,
                orig.width() - delta_x,
                orig.height() - delta_y
            )
        elif self.adjust_mode == 'resize_tr':
            new_rect_widget = QRect(
                orig.x(),
                orig.y() + delta_y,
                orig.width() + delta_x,
                orig.height() - delta_y
            )
        elif self.adjust_mode == 'resize_bl':
            new_rect_widget = QRect(
                orig.x() + delta_x,
                orig.y(),
                orig.width() - delta_x,
                orig.height() + delta_y
            )
        elif self.adjust_mode == 'resize_br':
            new_rect_widget = QRect(
                orig.x(),
                orig.y(),
                orig.width() + delta_x,
                orig.height() + delta_y
            )
        elif self.adjust_mode == 'resize_t':
            new_rect_widget = QRect(
                orig.x(),
                orig.y() + delta_y,
                orig.width(),
                orig.height() - delta_y
            )
        elif self.adjust_mode == 'resize_b':
            new_rect_widget = QRect(
                orig.x(),
                orig.y(),
                orig.width(),
                orig.height() + delta_y
            )
        elif self.adjust_mode == 'resize_l':
            new_rect_widget = QRect(
                orig.x() + delta_x,
                orig.y(),
                orig.width() - delta_x,
                orig.height()
            )
        elif self.adjust_mode == 'resize_r':
            new_rect_widget = QRect(
                orig.x(),
                orig.y(),
                orig.width() + delta_x,
                orig.height()
            )
        else:
            return
        
        # Clamp widget rect to pixmap bounds (for resize modes, prevent shrinking)
        if self.base_pixmap:
            pixmap_rect = self.base_pixmap.rect()
            pixmap_rect.moveCenter(self.rect().center())
            
            # For resize modes, constrain without shrinking
            if self.adjust_mode != 'move':
                # Constrain left edge
                if new_rect_widget.left() < pixmap_rect.left():
                    if self.adjust_mode in ['resize_tl', 'resize_bl', 'resize_l']:
                        # Adjusting left edge - stop at boundary
                        new_rect_widget.setLeft(pixmap_rect.left())
                    else:
                        # Adjusting right edge - move left edge to maintain size
                        new_rect_widget.setLeft(pixmap_rect.left())
                        new_rect_widget.setRight(pixmap_rect.left() + orig.width())
                
                # Constrain top edge
                if new_rect_widget.top() < pixmap_rect.top():
                    if self.adjust_mode in ['resize_tl', 'resize_tr', 'resize_t']:
                        new_rect_widget.setTop(pixmap_rect.top())
                    else:
                        new_rect_widget.setTop(pixmap_rect.top())
                        new_rect_widget.setBottom(pixmap_rect.top() + orig.height())
                
                # Constrain right edge
                if new_rect_widget.right() > pixmap_rect.right():
                    if self.adjust_mode in ['resize_tr', 'resize_br', 'resize_r']:
                        new_rect_widget.setRight(pixmap_rect.right())
                    else:
                        new_rect_widget.setRight(pixmap_rect.right())
                        new_rect_widget.setLeft(pixmap_rect.right() - orig.width())
                
                # Constrain bottom edge
                if new_rect_widget.bottom() > pixmap_rect.bottom():
                    if self.adjust_mode in ['resize_bl', 'resize_br', 'resize_b']:
                        new_rect_widget.setBottom(pixmap_rect.bottom())
                    else:
                        new_rect_widget.setBottom(pixmap_rect.bottom())
                        new_rect_widget.setTop(pixmap_rect.bottom() - orig.height())
            else:
                # For move mode, already handled above
                pass
        
        # Ensure minimum size
        if new_rect_widget.width() < 10:
            if self.adjust_mode in ['resize_tl', 'resize_bl', 'resize_l']:
                new_rect_widget.setLeft(new_rect_widget.right() - 10)
            else:
                new_rect_widget.setRight(new_rect_widget.left() + 10)
        if new_rect_widget.height() < 10:
            if self.adjust_mode in ['resize_tl', 'resize_tr', 'resize_t']:
                new_rect_widget.setTop(new_rect_widget.bottom() - 10)
            else:
                new_rect_widget.setBottom(new_rect_widget.top() + 10)
        
        self.crop_rect_widget = new_rect_widget
        
        # Convert back to frame coordinates
        top_left_frame = self.widget_to_frame_coords(new_rect_widget.topLeft())
        bottom_right_frame = self.widget_to_frame_coords(new_rect_widget.bottomRight())
        
        if top_left_frame and bottom_right_frame:
            # Get original frame rect size for reference
            orig_frame_rect = self.original_crop_rect if self.original_crop_rect else None
            orig_width = orig_frame_rect.width() if orig_frame_rect else (bottom_right_frame.x() - top_left_frame.x())
            orig_height = orig_frame_rect.height() if orig_frame_rect else (bottom_right_frame.y() - top_left_frame.y())
            
            # Clamp to frame bounds while maintaining size for move mode
            if self.adjust_mode == 'move':
                x1 = max(0, min(top_left_frame.x(), frame_width - orig_width))
                y1 = max(0, min(top_left_frame.y(), frame_height - orig_height))
                x2 = x1 + orig_width
                y2 = y1 + orig_height
                
                # Ensure we don't exceed bounds
                if x2 > frame_width:
                    x1 = frame_width - orig_width
                    x2 = frame_width
                if y2 > frame_height:
                    y1 = frame_height - orig_height
                    y2 = frame_height
            else:
                # For resize modes, clamp normally
                x1 = max(0, min(top_left_frame.x(), frame_width - 1))
                y1 = max(0, min(top_left_frame.y(), frame_height - 1))
                x2 = max(x1 + 1, min(bottom_right_frame.x(), frame_width))
                y2 = max(y1 + 1, min(bottom_right_frame.y(), frame_height))
            
            # Ensure minimum size and valid bounds
            if x2 <= x1:
                x2 = min(x1 + 1, frame_width)
            if y2 <= y1:
                y2 = min(y1 + 1, frame_height)
            
            # Final validation - ensure crop is completely within frame
            if x1 < 0 or y1 < 0 or x2 > frame_width or y2 > frame_height:
                # Adjust to fit within bounds
                if x1 < 0:
                    x2 = x2 - x1
                    x1 = 0
                if y1 < 0:
                    y2 = y2 - y1
                    y1 = 0
                if x2 > frame_width:
                    x1 = max(0, x1 - (x2 - frame_width))
                    x2 = frame_width
                if y2 > frame_height:
                    y1 = max(0, y1 - (y2 - frame_height))
                    y2 = frame_height
            
            # Apply constraints if enabled
            if self.lock_size and self.locked_size:
                x1, y1, x2, y2 = self.apply_size_constraint(x1, y1, x2, y2, self.locked_size)
            elif self.lock_aspect_ratio and self.aspect_ratio:
                x1, y1, x2, y2 = self.apply_aspect_ratio_constraint(x1, y1, x2, y2, self.aspect_ratio)
            
            # Re-clamp to frame bounds after constraint application
            # For move mode with locked size, maintain size
            if self.adjust_mode == 'move' and (self.lock_size or self.lock_aspect_ratio):
                final_width = x2 - x1
                final_height = y2 - y1
                x1 = max(0, min(x1, frame_width - final_width))
                y1 = max(0, min(y1, frame_height - final_height))
                x2 = x1 + final_width
                y2 = y1 + final_height
            else:
                x1 = max(0, min(x1, frame_width - 1))
                y1 = max(0, min(y1, frame_height - 1))
                x2 = max(0, min(x2, frame_width))
                y2 = max(0, min(y2, frame_height))
            
            self.crop_rect = QRect(x1, y1, x2 - x1, y2 - y1)
            
            # Update widget coordinates
            top_left_widget = self.frame_to_widget_coords(self.crop_rect.topLeft())
            bottom_right_widget = self.frame_to_widget_coords(self.crop_rect.bottomRight())
            if top_left_widget and bottom_right_widget:
                self.crop_rect_widget = QRect(top_left_widget, bottom_right_widget)
            
            self.crop_changed.emit(self.crop_rect)
        
        self.update()
    
    def set_shadow_count(self, count):
        """Set the number of shadow crop segments."""
        self.shadow_count = count
        if self.crop_rect:
            self.update_shadow_crops(count)
            self.update_display()
    
    def apply_aspect_ratio_constraint(self, x1, y1, x2, y2, aspect_ratio):
        """Apply aspect ratio constraint to crop rectangle."""
        if aspect_ratio is None:
            return x1, y1, x2, y2
        
        width = x2 - x1
        height = y2 - y1
        target_ratio = aspect_ratio[0] / aspect_ratio[1]
        current_ratio = width / height if height > 0 else 0
        
        if current_ratio > target_ratio:
            # Too wide, adjust height
            new_height = int(width / target_ratio)
            y2 = y1 + new_height
        else:
            # Too tall, adjust width
            new_width = int(height * target_ratio)
            x2 = x1 + new_width
        
        return x1, y1, x2, y2
    
    def apply_size_constraint(self, x1, y1, x2, y2, locked_size):
        """Apply size constraint to crop rectangle."""
        if locked_size is None:
            return x1, y1, x2, y2
        
        target_width, target_height = locked_size
        x2 = x1 + target_width
        y2 = y1 + target_height
        
        return x1, y1, x2, y2
    
    def update_crop_rect(self):
        """Update crop rectangle from start and end points, constrained to frame bounds."""
        if self.start_point and self.end_point and self.current_frame is not None:
            frame_height, frame_width = self.current_frame.shape[:2]
            
            # Get raw coordinates
            x1 = min(self.start_point.x(), self.end_point.x())
            y1 = min(self.start_point.y(), self.end_point.y())
            x2 = max(self.start_point.x(), self.end_point.x())
            y2 = max(self.start_point.y(), self.end_point.y())
            
            # Apply size constraint if locked
            if self.lock_size and self.locked_size:
                x1, y1, x2, y2 = self.apply_size_constraint(x1, y1, x2, y2, self.locked_size)
            # Apply aspect ratio constraint if locked
            elif self.lock_aspect_ratio and self.aspect_ratio:
                x1, y1, x2, y2 = self.apply_aspect_ratio_constraint(x1, y1, x2, y2, self.aspect_ratio)
            
            # Clamp to frame boundaries
            x1 = max(0, min(x1, frame_width - 1))
            y1 = max(0, min(y1, frame_height - 1))
            x2 = max(0, min(x2, frame_width))
            y2 = max(0, min(y2, frame_height))
            
            # Ensure minimum size (at least 1x1)
            if x2 <= x1:
                x2 = min(x1 + 1, frame_width)
            if y2 <= y1:
                y2 = min(y1 + 1, frame_height)
            
            self.crop_rect = QRect(x1, y1, x2 - x1, y2 - y1)
            
            # Update widget coordinates for drawing (clamped to pixmap bounds)
            if self.start_point_widget and self.end_point_widget:
                pixmap_rect = self.base_pixmap.rect() if self.base_pixmap else QRect()
                pixmap_rect.moveCenter(self.rect().center())
                
                x1_w = min(self.start_point_widget.x(), self.end_point_widget.x())
                y1_w = min(self.start_point_widget.y(), self.end_point_widget.y())
                x2_w = max(self.start_point_widget.x(), self.end_point_widget.x())
                y2_w = max(self.start_point_widget.y(), self.end_point_widget.y())
                
                # Clamp widget coordinates to pixmap bounds
                x1_w = max(pixmap_rect.left(), min(x1_w, pixmap_rect.right()))
                y1_w = max(pixmap_rect.top(), min(y1_w, pixmap_rect.bottom()))
                x2_w = max(pixmap_rect.left(), min(x2_w, pixmap_rect.right()))
                y2_w = max(pixmap_rect.top(), min(y2_w, pixmap_rect.bottom()))
                
                # Ensure minimum size
                if x2_w <= x1_w:
                    x2_w = min(x1_w + 1, pixmap_rect.right())
                if y2_w <= y1_w:
                    y2_w = min(y1_w + 1, pixmap_rect.bottom())
                
                self.crop_rect_widget = QRect(x1_w, y1_w, x2_w - x1_w, y2_w - y1_w)
            
            self.crop_changed.emit(self.crop_rect)
            # Update shadow crops when main crop changes
            self.update_shadow_crops(self.shadow_count)
    
    def update_shadow_crops(self, num_segments):
        """Update shadow crop rectangles based on number of segments."""
        if not self.crop_rect or num_segments <= 1:
            self.shadow_crop_rects = []
            self.shadow_crop_rects_widget = []
            return
        
        self.shadow_crop_rects = []
        self.shadow_crop_rects_widget = []
        
        crop_width = self.crop_rect.width()
        crop_height = self.crop_rect.height()
        crop_x = self.crop_rect.x()
        crop_y = self.crop_rect.y()
        
        frame_height, frame_width = self.current_frame.shape[:2]
        
        # Create shadow crops to the right of the main crop
        for i in range(1, num_segments):
            shadow_x = crop_x + (crop_width * i)
            
            # Check if shadow crop would fit within frame bounds
            if shadow_x + crop_width <= frame_width:
                shadow_rect = QRect(shadow_x, crop_y, crop_width, crop_height)
                self.shadow_crop_rects.append(shadow_rect)
                
                # Convert to widget coordinates
                top_left_widget = self.frame_to_widget_coords(shadow_rect.topLeft())
                bottom_right_widget = self.frame_to_widget_coords(shadow_rect.bottomRight())
                if top_left_widget and bottom_right_widget:
                    shadow_rect_widget = QRect(top_left_widget, bottom_right_widget)
                    self.shadow_crop_rects_widget.append(shadow_rect_widget)
    
    def clear_crop(self):
        """Clear the crop selection."""
        self.crop_rect = None
        self.crop_rect_widget = None
        self.shadow_crop_rects = []
        self.shadow_crop_rects_widget = []
        self.start_point = None
        self.end_point = None
        self.start_point_widget = None
        self.end_point_widget = None
        self.update_display()
    
    def resizeEvent(self, event):
        """Handle widget resize."""
        super().resizeEvent(event)
        if self.current_frame is not None:
            self.update_base_pixmap()
            # Recalculate crop rect widget coordinates
            if self.crop_rect:
                top_left_widget = self.frame_to_widget_coords(self.crop_rect.topLeft())
                bottom_right_widget = self.frame_to_widget_coords(self.crop_rect.bottomRight())
                self.crop_rect_widget = QRect(top_left_widget, bottom_right_widget)
                # Recalculate shadow crop widget coordinates
                self.update_shadow_crops(self.shadow_count)
        self.update_display()


class ExportDialog(QDialog):
    """Dialog for export quality settings."""
    
    def __init__(self, parent=None, locale="en_US"):
        super().__init__(parent)
        self.locale = locale
        self.setWindowTitle(tr("export_settings", locale))
        self.setModal(True)
        
        layout = QFormLayout(self)
        
        # Quality preset
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            tr("high", locale), tr("medium", locale), tr("low", locale), tr("custom_quality", locale)
        ])
        self.quality_combo.currentTextChanged.connect(self.on_quality_changed)
        layout.addRow(f"{tr('quality_preset', locale)}:", self.quality_combo)
        
        # Bitrate (Mbps)
        self.bitrate_spin = QSpinBox()
        self.bitrate_spin.setRange(1, 100)
        self.bitrate_spin.setValue(10)
        self.bitrate_spin.setSuffix(" Mbps")
        layout.addRow(f"{tr('bitrate', locale)}:", self.bitrate_spin)
        
        # Codec
        self.codec_combo = QComboBox()
        self.codec_combo.addItems(["H.264", "H.265 (HEVC)", "MPEG-4"])
        layout.addRow(f"{tr('codec', locale)}:", self.codec_combo)
        
        # FPS
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(30)
        self.fps_spin.setSuffix(" fps")
        layout.addRow(f"{tr('frame_rate', locale)}:", self.fps_spin)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.on_quality_changed(tr("high", locale))
    
    def on_quality_changed(self, quality):
        """Update settings based on quality preset."""
        high_text = tr("high", self.locale)
        medium_text = tr("medium", self.locale)
        low_text = tr("low", self.locale)
        
        if quality == high_text:
            self.bitrate_spin.setValue(20)
        elif quality == medium_text:
            self.bitrate_spin.setValue(10)
        elif quality == low_text:
            self.bitrate_spin.setValue(5)
        # Custom: keep current value
    
    def get_settings(self):
        """Get export settings."""
        codec_map = {
            "H.264": "mp4v",
            "H.265 (HEVC)": "hevc",
            "MPEG-4": "mp4v"
        }
        return {
            "bitrate": self.bitrate_spin.value() * 1000000,  # Convert to bps
            "codec": codec_map[self.codec_combo.currentText()],
            "fps": self.fps_spin.value()
        }


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.locale = "en_US"  # Current locale
        self.setWindowTitle(tr("window_title", self.locale))
        self.setGeometry(100, 100, 1200, 800)
        
        # Video state
        self.video_path = None
        self.video_cap = None
        self.current_frame_idx = 0
        self.total_frames = 0
        self.fps = 30
        self.rotation = 0  # 0, 90, 180, 270
        self.crop_rect = None
        self.first_frame = None  # Cached first frame for crop mode
        self.crop_mode_enabled = True  # Always use first frame for cropping
        self.crop_aspect_ratio = None  # (width, height) tuple or None
        self.shadow_count = 1  # Number of shadow crop segments
        
        # Timer for playback
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.next_frame)
        self.is_playing = False
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Top toolbar
        toolbar_layout = QHBoxLayout()
        
        self.import_btn = QPushButton(tr("import_video", self.locale))
        self.import_btn.clicked.connect(self.import_video)
        self.import_btn.setStyleSheet("padding: 8px 16px; font-size: 14px;")
        toolbar_layout.addWidget(self.import_btn)
        
        toolbar_layout.addStretch()
        
        # Language toggle buttons
        lang_group = QGroupBox("Language")
        lang_layout = QHBoxLayout()
        
        self.lang_en_btn = QPushButton(get_language_name("en_US"))
        self.lang_en_btn.setCheckable(True)
        self.lang_en_btn.setChecked(True)
        self.lang_en_btn.clicked.connect(lambda: self.set_locale("en_US"))
        lang_layout.addWidget(self.lang_en_btn)
        
        self.lang_cn_btn = QPushButton(get_language_name("zh_CN"))
        self.lang_cn_btn.setCheckable(True)
        self.lang_cn_btn.clicked.connect(lambda: self.set_locale("zh_CN"))
        lang_layout.addWidget(self.lang_cn_btn)
        
        self.lang_tw_btn = QPushButton(get_language_name("zh_TW"))
        self.lang_tw_btn.setCheckable(True)
        self.lang_tw_btn.clicked.connect(lambda: self.set_locale("zh_TW"))
        lang_layout.addWidget(self.lang_tw_btn)
        
        lang_group.setLayout(lang_layout)
        toolbar_layout.addWidget(lang_group)
        
        # Rotation controls
        self.rotation_group = QGroupBox(tr("rotation", self.locale))
        rotation_layout = QHBoxLayout()
        
        self.rotate_left_btn = QPushButton(tr("rotate_left", self.locale))
        self.rotate_left_btn.clicked.connect(self.rotate_left)
        rotation_layout.addWidget(self.rotate_left_btn)
        
        self.rotate_right_btn = QPushButton(tr("rotate_right", self.locale))
        self.rotate_right_btn.clicked.connect(self.rotate_right)
        rotation_layout.addWidget(self.rotate_right_btn)
        
        self.rotate_180_btn = QPushButton("180°")
        self.rotate_180_btn.clicked.connect(lambda: self.rotate_video(180))
        rotation_layout.addWidget(self.rotate_180_btn)
        
        self.reset_rotation_btn = QPushButton(tr("reset", self.locale))
        self.reset_rotation_btn.clicked.connect(lambda: self.rotate_video(0))
        rotation_layout.addWidget(self.reset_rotation_btn)
        
        self.rotation_group.setLayout(rotation_layout)
        toolbar_layout.addWidget(self.rotation_group)
        
        main_layout.addLayout(toolbar_layout)
        
        # Video preview area
        preview_layout = QHBoxLayout()
        
        self.preview_widget = VideoPreviewWidget()
        self.preview_widget.crop_changed.connect(self.on_crop_changed)
        preview_layout.addWidget(self.preview_widget, stretch=3)
        
        # Controls panel
        controls_panel = QWidget()
        controls_layout = QVBoxLayout(controls_panel)
        
        # Playback controls
        self.playback_group = QGroupBox(tr("playback", self.locale))
        playback_layout = QVBoxLayout()
        
        self.play_btn = QPushButton(tr("play", self.locale))
        self.play_btn.clicked.connect(self.toggle_playback)
        playback_layout.addWidget(self.play_btn)
        
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.valueChanged.connect(self.seek_frame)
        playback_layout.addWidget(self.frame_slider)
        
        self.frame_label = QLabel(f"{tr('frame', self.locale)}: 0 / 0")
        playback_layout.addWidget(self.frame_label)
        
        self.playback_group.setLayout(playback_layout)
        controls_layout.addWidget(self.playback_group)
        
        # Crop controls
        self.crop_group = QGroupBox(tr("crop", self.locale))
        crop_layout = QVBoxLayout()
        
        self.crop_info_label = QLabel(tr("drag_to_select", self.locale))
        crop_layout.addWidget(self.crop_info_label)
        
        # Note: First frame is always used during crop selection for better performance
        
        # Aspect ratio controls
        self.aspect_ratio_label = QLabel(f"{tr('aspect_ratio', self.locale)}:")
        crop_layout.addWidget(self.aspect_ratio_label)
        
        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.addItems([
            tr("free", self.locale), "16:9", "4:3", "1:1", "21:9", "9:16", "3:4", tr("custom", self.locale)
        ])
        self.aspect_ratio_combo.currentTextChanged.connect(self.on_aspect_ratio_changed)
        crop_layout.addWidget(self.aspect_ratio_combo)
        
        # Custom aspect ratio inputs
        custom_ratio_layout = QHBoxLayout()
        custom_ratio_label = QLabel(f"{tr('custom_ratio', self.locale)}:")
        custom_ratio_layout.addWidget(custom_ratio_label)
        
        self.custom_width_spin = QSpinBox()
        self.custom_width_spin.setRange(1, 1000)
        self.custom_width_spin.setValue(16)
        self.custom_width_spin.setToolTip("Width ratio")
        self.custom_width_spin.valueChanged.connect(self.on_custom_ratio_changed)
        custom_ratio_layout.addWidget(self.custom_width_spin)
        
        ratio_separator = QLabel(":")
        custom_ratio_layout.addWidget(ratio_separator)
        
        self.custom_height_spin = QSpinBox()
        self.custom_height_spin.setRange(1, 1000)
        self.custom_height_spin.setValue(9)
        self.custom_height_spin.setToolTip("Height ratio")
        self.custom_height_spin.valueChanged.connect(self.on_custom_ratio_changed)
        custom_ratio_layout.addWidget(self.custom_height_spin)
        
        self.custom_ratio_widget = QWidget()
        self.custom_ratio_widget.setLayout(custom_ratio_layout)
        self.custom_ratio_widget.setVisible(False)  # Hidden by default
        crop_layout.addWidget(self.custom_ratio_widget)
        
        self.lock_aspect_checkbox = QCheckBox(tr("lock_aspect_ratio", self.locale))
        self.lock_aspect_checkbox.toggled.connect(self.on_lock_aspect_toggled)
        crop_layout.addWidget(self.lock_aspect_checkbox)
        
        # Shadow cropping controls
        self.shadow_label = QLabel(f"{tr('number_of_segments', self.locale)}:")
        crop_layout.addWidget(self.shadow_label)
        
        self.shadow_count_spin = QSpinBox()
        self.shadow_count_spin.setRange(1, 10)
        self.shadow_count_spin.setValue(1)
        self.shadow_count_spin.setToolTip("Number of adjacent crop segments to extract")
        self.shadow_count_spin.valueChanged.connect(self.on_shadow_count_changed)
        crop_layout.addWidget(self.shadow_count_spin)
        
        self.clear_crop_btn = QPushButton(tr("clear_crop", self.locale))
        self.clear_crop_btn.clicked.connect(self.clear_crop)
        crop_layout.addWidget(self.clear_crop_btn)
        
        self.crop_group.setLayout(crop_layout)
        controls_layout.addWidget(self.crop_group)
        
        controls_layout.addStretch()
        
        preview_layout.addWidget(controls_panel, stretch=1)
        main_layout.addLayout(preview_layout)
        
        # Bottom toolbar
        bottom_layout = QHBoxLayout()
        
        bottom_layout.addStretch()
        
        self.export_btn = QPushButton(tr("export_video", self.locale))
        self.export_btn.clicked.connect(self.export_video)
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet("padding: 10px 20px; font-size: 16px; font-weight: bold;")
        bottom_layout.addWidget(self.export_btn)
        
        main_layout.addLayout(bottom_layout)
    
    def set_locale(self, locale):
        """Set the application locale and update UI."""
        if locale not in ["en_US", "zh_CN", "zh_TW"]:
            return
        
        self.locale = locale
        
        # Update language button states
        self.lang_en_btn.setChecked(locale == "en_US")
        self.lang_cn_btn.setChecked(locale == "zh_CN")
        self.lang_tw_btn.setChecked(locale == "zh_TW")
        
        # Update all UI strings
        self.update_ui()
    
    def update_ui(self):
        """Update all UI strings based on current locale."""
        # Window title
        self.setWindowTitle(tr("window_title", self.locale))
        
        # Top toolbar
        self.import_btn.setText(tr("import_video", self.locale))
        self.rotation_group.setTitle(tr("rotation", self.locale))
        self.rotate_left_btn.setText(tr("rotate_left", self.locale))
        self.rotate_right_btn.setText(tr("rotate_right", self.locale))
        self.reset_rotation_btn.setText(tr("reset", self.locale))
        
        # Playback controls
        self.playback_group.setTitle(tr("playback", self.locale))
        if self.is_playing:
            self.play_btn.setText(tr("pause", self.locale))
        else:
            self.play_btn.setText(tr("play", self.locale))
        
        # Update frame label
        if self.total_frames > 0:
            self.frame_label.setText(f"{tr('frame', self.locale)}: {self.current_frame_idx + 1} / {self.total_frames}")
        
        # Crop controls
        self.crop_group.setTitle(tr("crop", self.locale))
        self.crop_info_label.setText(tr("drag_to_select", self.locale))
        self.aspect_ratio_label.setText(f"{tr('aspect_ratio', self.locale)}:")
        
        # Update aspect ratio combo
        current_selection = self.aspect_ratio_combo.currentText()
        self.aspect_ratio_combo.clear()
        self.aspect_ratio_combo.addItems([
            tr("free", self.locale), "16:9", "4:3", "1:1", "21:9", "9:16", "3:4", tr("custom", self.locale)
        ])
        # Try to restore selection
        if current_selection in ["Free", tr("free", "en_US")]:
            self.aspect_ratio_combo.setCurrentText(tr("free", self.locale))
        elif current_selection in ["Custom", tr("custom", "en_US")]:
            self.aspect_ratio_combo.setCurrentText(tr("custom", self.locale))
        else:
            # For numeric ratios, try to find matching item
            for i in range(self.aspect_ratio_combo.count()):
                if self.aspect_ratio_combo.itemText(i) == current_selection:
                    self.aspect_ratio_combo.setCurrentIndex(i)
                    break
        
        # Custom ratio label
        custom_ratio_label = self.custom_ratio_widget.findChild(QLabel)
        if custom_ratio_label:
            custom_ratio_label.setText(f"{tr('custom_ratio', self.locale)}:")
        
        self.lock_aspect_checkbox.setText(tr("lock_aspect_ratio", self.locale))
        self.shadow_label.setText(f"{tr('number_of_segments', self.locale)}:")
        self.clear_crop_btn.setText(tr("clear_crop", self.locale))
        
        # Bottom toolbar
        self.export_btn.setText(tr("export_video", self.locale))
        
        # Update preview widget text if no video loaded
        if self.video_cap is None and self.preview_widget.current_frame is None:
            self.preview_widget.setText(tr("no_video_loaded", self.locale))
    
    def import_video(self):
        """Import a video file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("import_video_dialog", self.locale),
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm);;All Files (*)"
        )
        
        if file_path:
            self.video_path = file_path
            self.video_cap = cv2.VideoCapture(file_path)
            
            if not self.video_cap.isOpened():
                QMessageBox.critical(self, tr("error", self.locale), tr("failed_to_open", self.locale))
                return
            
            self.total_frames = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 30
            self.current_frame_idx = 0
            
            self.frame_slider.setMaximum(max(0, self.total_frames - 1))
            self.frame_slider.setValue(0)
            
            self.rotation = 0
            self.crop_rect = None
            self.preview_widget.clear_crop()
            
            # Cache first frame for crop mode
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, first_frame = self.video_cap.read()
            if ret:
                first_frame = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)
                self.first_frame = first_frame.copy()
            
            self.export_btn.setEnabled(True)
            self.load_frame(0)
    
    def load_frame(self, frame_idx):
        """Load a specific frame from the video."""
        if self.video_cap is None:
            return
        
        # Always use first frame when there's a crop selection or when drawing crop
        # This provides better performance and consistency
        if (self.preview_widget.drawing or self.preview_widget.crop_rect is not None) and self.first_frame is not None:
            frame = self.first_frame.copy()
            self.current_frame_idx = frame_idx  # Keep track of actual frame for display
        else:
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = self.video_cap.read()
            
            if not ret:
                return
            
            self.current_frame_idx = frame_idx
            
            # Convert BGR to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Apply rotation
        frame = self.apply_rotation(frame)
        
        self.preview_widget.set_frame(frame)
        self.frame_label.setText(f"{tr('frame', self.locale)}: {frame_idx + 1} / {self.total_frames}")
        self.frame_slider.setValue(frame_idx)
    
    def apply_rotation(self, frame):
        """Apply rotation to frame."""
        if self.rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif self.rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame
    
    def rotate_left(self):
        """Rotate video 90° counterclockwise (left)."""
        # Rotate left = subtract 90° (or add 270°)
        new_rotation = (self.rotation - 90) % 360
        self.rotate_video(new_rotation)
    
    def rotate_right(self):
        """Rotate video 90° clockwise (right)."""
        # Rotate right = add 90°
        new_rotation = (self.rotation + 90) % 360
        self.rotate_video(new_rotation)
    
    def rotate_video(self, degrees):
        """Rotate the video."""
        self.rotation = degrees
        # Clear crop selection when rotation changes (dimensions change)
        self.crop_rect = None
        self.preview_widget.clear_crop()
        
        # Update first frame cache if it exists
        if self.first_frame is not None:
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, first_frame = self.video_cap.read()
            if ret:
                first_frame = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)
                self.first_frame = first_frame.copy()
        if self.video_cap is not None:
            self.load_frame(self.current_frame_idx)
    
    
    def on_aspect_ratio_changed(self, ratio_text):
        """Handle aspect ratio selection change."""
        free_text = tr("free", self.locale)
        custom_text = tr("custom", self.locale)
        
        ratio_map = {
            "16:9": (16, 9),
            "4:3": (4, 3),
            "1:1": (1, 1),
            "21:9": (21, 9),
            "9:16": (9, 16),
            "3:4": (3, 4),
        }
        
        # Show/hide custom ratio inputs
        if ratio_text == custom_text:
            self.custom_ratio_widget.setVisible(True)
            # Use current custom values
            custom_width = self.custom_width_spin.value()
            custom_height = self.custom_height_spin.value()
            self.crop_aspect_ratio = (custom_width, custom_height)
            self.lock_aspect_checkbox.setChecked(True)
        else:
            self.custom_ratio_widget.setVisible(False)
        
        # Clear crop selection when aspect ratio changes
        old_ratio = self.crop_aspect_ratio
        if ratio_text == free_text:
            self.crop_aspect_ratio = None
            self.lock_aspect_checkbox.setChecked(False)
        elif ratio_text != custom_text:
            self.crop_aspect_ratio = ratio_map.get(ratio_text)
            # Automatically enable lock when a ratio is selected
            self.lock_aspect_checkbox.setChecked(True)
        
        # Clear crop if ratio actually changed
        if old_ratio != self.crop_aspect_ratio:
            self.crop_rect = None
            self.preview_widget.clear_crop()
        
        # Update preview widget - always lock when ratio is selected
        self.preview_widget.aspect_ratio = self.crop_aspect_ratio
        self.preview_widget.lock_aspect_ratio = (self.crop_aspect_ratio is not None)
    
    def on_custom_ratio_changed(self):
        """Handle custom aspect ratio input change."""
        custom_text = tr("custom", self.locale)
        if self.aspect_ratio_combo.currentText() == custom_text:
            custom_width = self.custom_width_spin.value()
            custom_height = self.custom_height_spin.value()
            
            # Clear crop selection when custom ratio changes
            old_ratio = self.crop_aspect_ratio
            self.crop_aspect_ratio = (custom_width, custom_height)
            
            if old_ratio != self.crop_aspect_ratio:
                self.crop_rect = None
                self.preview_widget.clear_crop()
            
            # Update preview widget
            self.preview_widget.aspect_ratio = self.crop_aspect_ratio
            self.preview_widget.lock_aspect_ratio = True
    
    def on_lock_aspect_toggled(self, locked):
        """Handle aspect ratio lock toggle."""
        # If unlocking and a ratio is selected, clear the ratio
        if not locked:
            self.crop_aspect_ratio = None
            self.aspect_ratio_combo.setCurrentText(tr("free", self.locale))
        
        self.preview_widget.lock_aspect_ratio = locked
        self.preview_widget.aspect_ratio = self.crop_aspect_ratio if locked else None
        
        # If there's an existing crop, update it
        if self.preview_widget.crop_rect:
            self.preview_widget.update_crop_rect()
    
    def on_shadow_count_changed(self, count):
        """Handle shadow count change."""
        self.shadow_count = count
        self.preview_widget.set_shadow_count(count)
    
    def on_crop_changed(self, rect):
        """Handle crop rectangle change."""
        self.crop_rect = rect
        # Update shadow crops when main crop changes
        if self.preview_widget:
            self.preview_widget.update_shadow_crops(self.shadow_count)
    
    def clear_crop(self):
        """Clear the crop selection."""
        self.crop_rect = None
        self.preview_widget.clear_crop()
    
    def toggle_playback(self):
        """Toggle video playback."""
        if self.video_cap is None:
            return
        
        if self.is_playing:
            self.playback_timer.stop()
            self.is_playing = False
            self.play_btn.setText("Play")
        else:
            interval = int(1000 / self.fps)
            self.playback_timer.start(interval)
            self.is_playing = True
            self.play_btn.setText("Pause")
    
    def next_frame(self):
        """Advance to next frame during playback."""
        if self.current_frame_idx < self.total_frames - 1:
            self.load_frame(self.current_frame_idx + 1)
        else:
            self.toggle_playback()
    
    def seek_frame(self, frame_idx):
        """Seek to a specific frame."""
        if not self.is_playing:
            self.load_frame(frame_idx)
    
    def export_video(self):
        """Export the processed video."""
        if self.video_path is None:
            return
        
        # Show export dialog
        dialog = ExportDialog(self, self.locale)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        settings = dialog.get_settings()
        
        # Collect all crop rectangles (main + shadows)
        all_crop_rects = []
        if self.crop_rect:
            all_crop_rects.append(self.crop_rect)
            if self.preview_widget.shadow_crop_rects:
                all_crop_rects.extend(self.preview_widget.shadow_crop_rects)
        
        if not all_crop_rects:
            QMessageBox.warning(self, tr("no_selection", self.locale), tr("select_crop_area", self.locale))
            return
        
        # Get output file path
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("export_video_dialog", self.locale),
            "",
            "MP4 Files (*.mp4);;AVI Files (*.avi);;All Files (*)"
        )
        
        if not output_path:
            return
        
        # Initialize progress dialog to None
        progress_dialog = None
        
        try:
            # Calculate total frames across all segments
            temp_cap = cv2.VideoCapture(self.video_path)
            if not temp_cap.isOpened():
                QMessageBox.critical(self, tr("error", self.locale), tr("failed_to_open", self.locale))
                return
            total_frames_per_segment = int(temp_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            total_frames_all_segments = total_frames_per_segment * len(all_crop_rects)
            temp_cap.release()
            
            # Create progress dialog with progress bar
            progress_dialog = QProgressDialog(self)
            progress_dialog.setWindowTitle(tr("exporting", self.locale))
            progress_dialog.setLabelText(tr("exporting_video", self.locale))
            progress_dialog.setRange(0, total_frames_all_segments)
            progress_dialog.setValue(0)
            progress_dialog.setCancelButtonText("Cancel")
            progress_dialog.setMinimumDuration(0)  # Show immediately
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.show()
            QApplication.processEvents()
            # Export each segment
            exported_files = []
            base_path = Path(output_path)
            base_name = base_path.stem
            base_dir = base_path.parent
            extension = base_path.suffix
            overall_frame_count = 0
            
            for idx, crop_rect in enumerate(all_crop_rects):
                # Check if cancelled
                if progress_dialog.wasCanceled():
                    progress_dialog.close()
                    QMessageBox.information(self, tr("cancelled", self.locale), tr("export_cancelled", self.locale))
                    return
                
                # Generate output filename
                if len(all_crop_rects) > 1:
                    segment_path = base_dir / f"{base_name}_segment_{idx + 1}{extension}"
                else:
                    segment_path = base_path
                
                # Update progress dialog label
                progress_dialog.setLabelText(
                    tr("exporting_segment_progress", self.locale).format(idx + 1, len(all_crop_rects))
                )
                QApplication.processEvents()
                
                # Reopen video for each segment
                cap = cv2.VideoCapture(self.video_path)
                if not cap.isOpened():
                    raise Exception("Failed to open input video")
                
                # Get video properties
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS) or settings["fps"]
                
                # Apply rotation to dimensions
                if self.rotation == 90 or self.rotation == 270:
                    width, height = height, width
                
                # Use crop dimensions
                crop_width = crop_rect.width()
                crop_height = crop_rect.height()
                
                # Setup video writer
                fourcc = cv2.VideoWriter_fourcc(*settings["codec"][:4].upper())
                out = cv2.VideoWriter(str(segment_path), fourcc, settings["fps"], (crop_width, crop_height))
                
                frame_count = 0
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                
                while True:
                    # Check if cancelled
                    if progress_dialog.wasCanceled():
                        cap.release()
                        out.release()
                        progress_dialog.close()
                        QMessageBox.information(self, tr("cancelled", self.locale), tr("export_cancelled", self.locale))
                        return
                    
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # Apply rotation
                    frame = self.apply_rotation(frame)
                    
                    # Get frame dimensions after rotation
                    frame_height, frame_width = frame.shape[:2]
                    
                    # Apply crop with bounds checking
                    x = crop_rect.x()
                    y = crop_rect.y()
                    w = crop_rect.width()
                    h = crop_rect.height()
                    
                    # Clamp crop coordinates to frame bounds
                    x = max(0, min(x, frame_width - 1))
                    y = max(0, min(y, frame_height - 1))
                    w = min(w, frame_width - x)
                    h = min(h, frame_height - y)
                    
                    # Skip if crop is invalid
                    if w <= 0 or h <= 0:
                        continue
                    
                    frame = frame[y:y+h, x:x+w]
                    
                    # Frame is already in BGR from VideoCapture, no conversion needed
                    
                    # Validate frame before resizing
                    if frame.size == 0 or len(frame.shape) < 2:
                        continue
                    
                    # Resize if needed
                    if frame.shape[1] != crop_width or frame.shape[0] != crop_height:
                        if frame.shape[1] > 0 and frame.shape[0] > 0:
                            frame = cv2.resize(frame, (crop_width, crop_height))
                        else:
                            continue
                    
                    out.write(frame)
                    frame_count += 1
                    overall_frame_count += 1
                    
                    # Update progress bar (update every frame for smooth progress)
                    progress_dialog.setValue(overall_frame_count)
                    progress_dialog.setLabelText(
                        tr("exporting_segment_progress", self.locale).format(idx + 1, len(all_crop_rects)) + 
                        " - " + tr("processing_frames", self.locale).format(frame_count, total_frames)
                    )
                    QApplication.processEvents()
                
                cap.release()
                out.release()
                exported_files.append(str(segment_path))
            
            progress_dialog.close()
            
            if len(exported_files) > 1:
                files_list = "\n".join([f"  • {f}" for f in exported_files])
                QMessageBox.information(
                    self, 
                    tr("success", self.locale), 
                    f"{tr('exported_segments', self.locale).format(len(exported_files))}\n{files_list}"
                )
            else:
                QMessageBox.information(self, tr("success", self.locale), f"{tr('video_exported', self.locale)}\n{exported_files[0]}")
            
        except Exception as e:
            if progress_dialog is not None:
                progress_dialog.close()
            QMessageBox.critical(self, tr("export_error", self.locale), f"{tr('failed_to_export', self.locale)}\n{str(e)}")


def main():
    """Main function to run the application."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
