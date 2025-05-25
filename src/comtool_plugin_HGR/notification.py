from PyQt5.QtWidgets import QLabel, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QWidget, QStackedLayout
from PyQt5.QtCore import QPropertyAnimation, QTimer, Qt, QPoint, QEasingCurve, QParallelAnimationGroup, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QResizeEvent, QMouseEvent


class NotificationContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.notifications = []
        # 设置为覆盖层属性
        self.setWindowFlags(Qt.WindowType(Qt.Widget))
        # *** 关键修改：默认设置为鼠标穿透，但允许子控件接收事件 ***
        self.setAttribute(Qt.WidgetAttribute(Qt.WA_TransparentForMouseEvents), True)
        self.setStyleSheet("background: transparent; border: none;")

        # 初始化位置和大小
        if parent:
            self.setGeometry(parent.rect())
            self.raise_()  # 确保在最上层

        self.hide()  # 默认隐藏，有通知时才显示

    def resizeEvent(self, event: QResizeEvent):
        """当容器大小改变时重新排列通知"""
        super().resizeEvent(event)
        self._rearrange_notifications()

    def update_geometry(self):
        """更新容器几何尺寸以匹配父窗口"""
        if self.parent_widget:
            self.setGeometry(self.parent_widget.rect())
            self._rearrange_notifications()

    def add_notification(self, text):
        """添加新通知并置顶"""
        note = Notification(self)

        # 计算位置（右下角开始，向上堆叠）
        self._position_notification(note, len(self.notifications))

        # 显示通知
        note.show_notification(text)
        self.notifications.append(note)

        # 显示容器
        self.show()
        self.raise_()

        # 设置自动移除定时器
        QTimer.singleShot(3000, lambda: self._remove_notification(note))

    def _position_notification(self, notification, index):
        """计算并设置通知位置"""
        margin = 20  # 边距
        spacing = 10  # 通知间距

        # 从右下角开始定位
        x = self.width() - notification.width() - margin
        y = self.height() - notification.height() - margin - (index * (notification.height() + spacing))

        notification.move(max(0, x), max(0, y))

    def _remove_notification(self, note):
        """移除通知"""
        if note in self.notifications:
            self.notifications.remove(note)
            note.fade_out()

            # 重新排列剩余通知
            self._rearrange_notifications()

            # 如果没有通知了，隐藏容器
            if not self.notifications:
                self.hide()

    def _rearrange_notifications(self):
        """重新排列所有通知的位置"""
        for i, note in enumerate(self.notifications):
            if note.isVisible():
                target_x = self.width() - note.width() - 20
                target_y = self.height() - note.height() - 20 - (i * (note.height() + 10))

                # 使用动画平滑移动到新位置
                if note.pos() != QPoint(target_x, target_y):
                    anim = QPropertyAnimation(note, b"pos", note)
                    anim.setDuration(250)
                    anim.setStartValue(note.pos())
                    anim.setEndValue(QPoint(target_x, target_y))
                    anim.setEasingCurve(QEasingCurve.OutCubic)
                    anim.start()
                    # 保存动画引用防止被垃圾回收
                    note._rearrange_anim = anim


class Notification(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self._setup_ui()

    def _setup_ui(self):
        """设置通知样式"""
        self.setFixedSize(250, 70)
        
        # *** 关键修改：通知本身不设置鼠标穿透，可以接收点击事件 ***
        self.setAttribute(Qt.WidgetAttribute(Qt.WA_TransparentForMouseEvents), False)

        # 现代化样式
        self.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(76, 175, 80, 0.95),
                    stop:1 rgba(56, 142, 60, 0.95));
                border: none;
                border-radius: 12px;
                color: white;
                font-weight: 600;
                padding: 15px;
            }
            QLabel:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(81, 184, 86, 0.98),
                    stop:1 rgba(61, 151, 66, 0.98));
            }
        """)

        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        # 字体设置
        font = QFont("Microsoft YaHei", 11)
        font.setWeight(QFont.Medium)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag(Qt.AlignCenter))
        self.setWordWrap(True)

        self.hide()

    def show_notification(self, text):
        """显示通知（带渐入动画）"""
        self.setText(text)

        # 设置初始透明度和位置
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0)
        self.setGraphicsEffect(effect)

        # 从右侧滑入的起始位置
        start_pos = self.pos() + QPoint(50, 0)
        self.move(start_pos)

        self.show()

        # 创建组合动画
        anim_group = QParallelAnimationGroup(self)

        # 透明度动画
        opacity_anim = QPropertyAnimation(effect, b"opacity", self)
        opacity_anim.setDuration(400)
        opacity_anim.setStartValue(0)
        opacity_anim.setEndValue(1)
        opacity_anim.setEasingCurve(QEasingCurve.OutQuart)

        # 位置动画（从右侧滑入）
        pos_anim = QPropertyAnimation(self, b"pos", self)
        pos_anim.setDuration(400)
        pos_anim.setStartValue(start_pos)
        pos_anim.setEndValue(start_pos - QPoint(50, 0))
        pos_anim.setEasingCurve(QEasingCurve.OutQuart)

        anim_group.addAnimation(opacity_anim)
        anim_group.addAnimation(pos_anim)
        anim_group.start()

        # 保存动画引用
        self._show_anim = anim_group

    def fade_out(self):
        """渐隐退出动画"""
        if not self.isVisible():
            return

        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(1)
        self.setGraphicsEffect(effect)

        # 组合动画：透明度 + 右滑消失
        anim_group = QParallelAnimationGroup(self)

        # 透明度动画
        opacity_anim = QPropertyAnimation(effect, b"opacity", self)
        opacity_anim.setDuration(300)
        opacity_anim.setStartValue(1)
        opacity_anim.setEndValue(0)
        opacity_anim.setEasingCurve(QEasingCurve.InQuart)

        # 位置动画（向右滑出）
        pos_anim = QPropertyAnimation(self, b"pos", self)
        pos_anim.setDuration(300)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(self.pos() + QPoint(80, 0))
        pos_anim.setEasingCurve(QEasingCurve.InQuart)

        anim_group.addAnimation(opacity_anim)
        anim_group.addAnimation(pos_anim)
        anim_group.finished.connect(self._cleanup)
        anim_group.start()

        # 保存动画引用
        self._fade_anim = anim_group

    def _cleanup(self):
        """清理资源"""
        self.timer.stop()
        self.hide()
        self.deleteLater()

    def mousePressEvent(self, event):
        """点击通知可立即关闭"""
        if event.button() == Qt.LeftButton:
            self.fade_out()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        """鼠标悬停时的视觉反馈"""
        self.setCursor(Qt.PointingHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开时恢复默认光标"""
        self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)