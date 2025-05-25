import atexit
import os
import shutil
import tempfile
from dataclasses import dataclass
from time import perf_counter_ns
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QPushButton, QLineEdit, QGridLayout,
     QLabel,  QFileDialog, QMessageBox, QHBoxLayout, QProgressBar,
     QStackedLayout)
from PyQt5.QtGui import QFont, QTextCursor, QPainter, QColor, QBrush, QPen
from plugins.base import Plugin_Base
from PyQt5.QtCore import pyqtSignal, Qt, QSize, \
     QObject, QTimer
from i18n import _
from conn import ConnectionStatus
from COMTool.plugins.base import Plugin_Base
from COMTool.conn import ConnectionStatus
from data_processor import FloatFrameParser
from notification import NotificationContainer

def open_directory_dialog()-> str:
    return QFileDialog.getExistingDirectory(None,"选择目录","")

class EmittingStream(QObject):
    textWritten = pyqtSignal(str)

    def write(self, text):
        self.textWritten.emit(str(text))

@dataclass
class DatabaseInfo:
    data_set_name: str
    collection_date: str
    participant_id: str
    gesture_type: str
    collection_count: int
    sensor_type: str
    sampling_frequency: str
    encode_format: str
    annotation: str
    data_format: str

InitInfo = DatabaseInfo(
    data_set_name="手势识别项目 v1.0",
    collection_date="0000-00-00",
    participant_id="P000",
    gesture_type="<UNK>",
    collection_count=0,
    sensor_type="BNO08x",
    sampling_frequency="50Hz",
    encode_format="utf-8",
    annotation=f"{'#'*20}",
    data_format="timestamp,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z"
)


# 新增状态指示器组件
class StatusIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = False  # False: 红色, True: 绿色
        self.setFixedSize(20, 20)  # 设置固定大小

    def set_status(self, status: bool):
        """设置状态并刷新显示"""
        self.status = status
        self.update()  # 触发重绘

    def get_status(self):
        return self.status

    def paintEvent(self, event):
        """绘制状态圆"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # 抗锯齿

        # 设置颜色
        color = QColor(0, 255, 0) if self.status else QColor(255, 0, 0)  # 绿色或红色
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(0, 0, 0), 1))  # 黑色边框

        # 绘制圆形
        rect = self.rect().adjusted(2, 2, -2, -2)  # 留出边距
        painter.drawEllipse(rect)


class Plugin(Plugin_Base):
    id = "Seri_recor"
    name = ("Serial port recorder")
    updateSignal = pyqtSignal(str, object)
    writeSignal = pyqtSignal(tuple)
    flay_file_writer_paraChangedSignal = pyqtSignal(bool)
    flay_file_writer = False

    def __init__(self):
        super().__init__()
        self.path_to_file = None
        self.data_processor = FloatFrameParser()
        self.file_info = None
        self.flay_file_writer_paraChangedSignal.connect(self._write_status_changed)

    def onConnChanged(self, status:ConnectionStatus, msg:str):
        super().onConnChanged(status, msg)
        print("-- connection changed: {}, msg: {}".format(status, msg))

    def onWidgetMain(self, parent):
        """
            main widget, just return a QWidget object
        """
        self.widget = QWidget()
        widget1 = QWidget()
        stacklayout = QStackedLayout()
        layout1 = QVBoxLayout()
        layout2 = QHBoxLayout()

        # 创建参数设置 widget
        self.parameter_widget = ParameterSettingWidget(InitInfo)
        self.parameter_widget.parameterChangedSignal.connect(self._update_file_info)

        # Progress bar prompt
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.setFixedSize(QSize(200, 20))

        # 创建状态指示器
        self.status_indicator = StatusIndicator()
        self.status_indicator.set_status(self.flay_file_writer)

        # 添加状态标签
        self.status_label = QLabel("记录状态:")
        self.status_label.setAlignment(Qt.AlignCenter)

        # 创建定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_progress)
        self.update_steps = 0

        grid_layout_buttons = self._init_buttons()

        # file writer module
        self.fileWriter = FileWriter(self)

        # receive widget
        font = QFont("")
        self.receiveArea = QTextEdit("")
        self.receiveArea.setReadOnly(True)
        self.receiveArea.setFont(font)
        self.receiveArea.setLineWrapMode(QTextEdit.NoWrap)
        self.receiveArea.setAlignment(Qt.AlignBottom)

        layout1.addLayout(layout2)
        layout1.addWidget(self.parameter_widget)
        layout1.addWidget(self.receiveArea)

        layout2.addWidget(self.progressBar)
        layout2.addWidget(self.status_label)
        layout2.addWidget(self.status_indicator)
        layout2.addLayout(grid_layout_buttons)

        widget1.setLayout(layout1)
        stacklayout.addWidget(widget1)
        self.widget.setLayout(stacklayout)
        self.notification_container = NotificationContainer(self.widget)

        # 连接信号
        self.updateSignal.connect(self.updateUI)
        self.writeSignal.connect(self.fileWriter.write_data)
        # 设置窗口大小变化处理
        self._setup_widget_resize_handler()


        return self.widget

    def _show_test_notification(self):
        """显示测试通知"""
        if hasattr(self, 'notification_container'):
            self.notification_container.add_notification("数据保存成功！")
            print("通知已触发")  # 调试用
        else:
            print("通知容器未初始化")

    # 重写 widget 的 resizeEvent 以更新通知容器
    def _setup_widget_resize_handler(self):
        """设置窗口大小变化处理"""
        # 保存原始的 resizeEvent
        original_resize = self.widget.resizeEvent

        def new_resize_event(event):
            # 调用原始事件处理
            if original_resize:
                original_resize(event)

            # 更新通知容器几何尺寸
            if hasattr(self, 'notification_container'):
                # 使用 QTimer.singleShot 确保在布局更新后执行
                QTimer.singleShot(0, self.notification_container.update_geometry)

        # 替换 resizeEvent
        self.widget.resizeEvent = new_resize_event

    def updateUI(self, data_type, data):
        '''
            UI thread
        '''
        if data_type == "receive":
            self.receiveArea.moveCursor(QTextCursor.End)
            # 将数据转换为十六进制字符串
            hex_data = ' '.join([f'{b:02X}' for b in data])
            self.receiveArea.insertPlainText(hex_data + "\n")
    
    def onReceived(self, data : bytes):
        '''
            call in receive thread, not UI thread
        '''
        super().onReceived(data)
        self.updateSignal.emit("receive", data)
        if self.flay_file_writer:
            data_set = self.data_processor.parse_frame(data)
            if data_set is not None :
                self.writeSignal.emit(data_set)

    def on_button_tmp_file_open_clicked_handle(self):
        # open in explorer
        tmp_file_path = self.fileWriter.get_tmp_file_path()
        if tmp_file_path:
            os.startfile(tmp_file_path)

    def on_button_tmp_file_save_handle(self):
        """按钮点击事件：打开文件对话框并保存文件"""
        # 弹出文件保存对话框
        if self.file_info is None:
            QMessageBox.warning(self.widget, "警告", "未设定基本信息")
            raise ValueError("未设定基本信息")
        default_file_name = (f"{self.file_info.gesture_type}_"
                             f"{self.file_info.participant_id}_"
                             f"{self.file_info.collection_count}.csv")
        default_file_path = os.path.join(os.path.expanduser("~\\Documents\\HGR_database"), default_file_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self.widget,  # 使用 self.widget 作为 QWidget 实例
            "选择保存位置",
            default_file_path,  # 默认从用户目录开始
            "文本文件 (*.csv);;所有文件 (*)"
        )

        if file_path:  # 如果用户未取消对话框
            if self.fileWriter.save_as_file(file_path, self.file_info):  # 使用 self.fileWriter 实例
                QMessageBox.information(self.widget, "成功", f"文件已保存到:\n{file_path}")
                print(f"文件已保存到:{file_path}")
                self.fileWriter.re_init()
                self.parameter_widget.increment_collection_count()
            else:
                QMessageBox.critical(self.widget, "错误", "文件保存失败！")

    def on_button_start_clicked_handle(self):
        self.update_steps = 0
        self.timer.start(30)
        self.flay_file_writer_paraChangedSignal.emit(True)
        self.flay_file_writer = True

    def _update_file_info(self, info: DatabaseInfo, para_name: str):
        self.file_info = info
        self.notification_container.add_notification(para_name)

    def _update_progress(self):
        self.update_steps += 1
        if self.update_steps <= 100:
            self.progressBar.setValue(self.update_steps)
        else:
            self.flay_file_writer_paraChangedSignal.emit(False)
            self.flay_file_writer = False
            self.timer.stop()

    def _write_status_changed(self, status: bool):
        self.status_indicator.set_status(status)
        if not status: # if completed one cycle
            self.on_button_tmp_file_save_handle()
            pass

    def _init_buttons(self) -> QGridLayout:
        # 按钮创建
        grid_layout_buttons = QGridLayout()
        grid_layout_buttons.setSpacing(10)

        # 设置网格大小
        GRID_COLS = 3  # 列数
        BUTTON_SIZE = QSize(80, 35)  # 统一按钮尺寸

        # 按钮配置列表：(按钮文字, 变量名, 处理方法名)
        button_configs = [
            ('开始', 'btn_play', 'on_button_start_clicked_handle'),
            ('打开临时文件', 'btn_tmp_file', 'on_button_tmp_file_open_clicked_handle'),
            ('保存文件', 'btn_save', 'on_button_tmp_file_save_handle'),
            ('显示通知', 'btn_notification', '_show_test_notification'),
        ]

        # 按顺序创建并添加按钮
        for i, (text, attr_name, handler_name) in enumerate(button_configs):
            # 计算网格位置
            row = i // GRID_COLS
            col = i % GRID_COLS

            # 创建按钮
            button = QPushButton(text)
            button.setFixedSize(BUTTON_SIZE)

            # 连接处理方法
            handler = getattr(self, handler_name)
            button.clicked.connect(handler)

            # 将按钮设置为实例属性
            setattr(self, attr_name, button)

            # 添加到网格布局
            grid_layout_buttons.addWidget(button, row, col)

        return grid_layout_buttons

    def onDel(self):
        self.fileWriter.close()  # 窗口关闭时手动清理

class FileWriter(QObject):
    acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z = 0, 0, 0, 0, 0, 0
    acc_ready = False
    gyro_ready = False
    def __init__(self, parent=None):
        super().__init__(parent)
        fd, self.temp_path = tempfile.mkstemp(suffix='.txt', text=True)
        self.temp_file = os.fdopen(fd, 'w+t')  # 转换为文件对象
        print("临时文件路径:", self.temp_path)
        self._format_header()

        atexit.register(self._cleanup)

    def re_init(self):
        self._cleanup()
        self.__init__()

    def add_header(self, info: DatabaseInfo):
        """初始化文件头"""
        self.write_to_head(
            f"# data_set_name:{info.data_set_name}\n"
            f"# collection_date:{info.collection_date}\n"
            f"# participant_id:{info.participant_id}\n"
            f"# gesture_type:{info.gesture_type}\n"
            f"# collection_count:{info.collection_count}\n"
            f"# sensor_type:{info.sensor_type}\n"
            f"# sampling_frequency:{info.sampling_frequency}\n"
            f"# encode_format:{info.encode_format}\n"
            f"#{info.annotation}\n"
            f"{info.data_format}\n"
        )

    def _format_header(self):
        header = (
            f"# data_set_name:{InitInfo.data_set_name}\n"
            f"# collection_date:{InitInfo.collection_date}\n"
            f"# participant_id:{InitInfo.participant_id}\n"
            f"# gesture_type:{InitInfo.gesture_type}\n"
            f"# collection_count:{InitInfo.collection_count}\n"
            f"# sensor_type:{InitInfo.sensor_type}\n"
            f"# sampling_frequency:{InitInfo.sampling_frequency}\n"
            f"# encode_format:{InitInfo.encode_format}\n"
            f"#{InitInfo.annotation}\n"
            f"{InitInfo.data_format}\n"
        )
        self.add_header(InitInfo)

    def write_to_head(self, text):
        """写入到临时文件开头
        warning:
            写入的文本会覆盖之前的内容, 请确保文件内容不会被覆盖
        """
        try:
            # 移动文件指针到文件开头
            self.temp_file.seek(0)
            # 写入文本数据
            self.temp_file.write(text + '\n')
            # 刷新缓冲区，确保数据写入文件
            self.temp_file.flush()
        except Exception as e:
            print(f"写入临时文件时出错: {e}")

    def write_data(self, data:tuple):
        """write data to file"""
        uint8_val, float1, float2, float3 = data
        if uint8_val == 0x01:
            self.acc_ready = True
            self.acc_x, self.acc_y, self.acc_z = float1, float2, float3
        elif uint8_val == 0x02:
            self.gyro_ready = True
            self.gyro_x, self.gyro_y, self.gyro_z = float1, float2, float3

        if self.acc_ready and self.gyro_ready:
            self.acc_ready = False
            self.gyro_ready = False
            self.write_to_end(
                f"{perf_counter_ns()},"
                f"{self.acc_x},{self.acc_y},{self.acc_z},{self.gyro_x},{self.gyro_y},{self.gyro_z}\n"
            )

    def write_to_end(self, text):
        """写入到临时文件末尾"""
        try:
            # 移动文件指针到文件末尾
            self.temp_file.seek(0, 2)
            # 写入文本数据
            self.temp_file.write(text)
            # 刷新缓冲区，确保数据写入文件
            self.temp_file.flush()
        except Exception as e:
            print(f"写入临时文件时出错: {e}")

    def read_text_from_temp_file(self):
        """从临时文件中读取文本数据"""
        try:
            # 移动文件指针到文件开头
            self.temp_file.seek(0)
            # 读取所有文本数据
            content = self.temp_file.read()
            return content
        except Exception as e:
            print(f"读取临时文件时出错: {e}")
            return ""

    def save_as_file(self, path: str, info:DatabaseInfo) -> bool:
        """
        [手势类型]_[参与者ID]_[采集次数]_[时间戳].扩展名

        Args:
            path (str): 目标文件路径
            info (DatabaseInfo): contains basic info of data set
        """
        try:
            self.add_header(info)
            self.temp_file.flush()
            shutil.copy(self.temp_path, path)
            return True
        except Exception as e:
            print(f"另存文件失败: {e}")
            return False

    def get_tmp_file_path(self) -> str:
        temp_file_path = self.temp_path
        temp_folder = os.path.dirname(temp_file_path)
        return temp_folder

    def _cleanup(self):
        """清理临时文件"""
        if hasattr(self, 'temp_file') and not self.temp_file.closed:
            self.temp_file.close()

        if hasattr(self, 'temp_path') and os.path.exists(self.temp_path):
            try:
                os.unlink(self.temp_path)  # 删除临时文件
                print(f"已删除临时文件: {self.temp_path}")
            except Exception as e:
                print(f"删除临时文件失败: {e}")

    def close(self):
        self._cleanup()

class ParameterSettingWidget(QWidget):
    parameterChangedSignal = pyqtSignal(DatabaseInfo, str)

    def __init__(self, init_info: DatabaseInfo):
        super().__init__()
        self.init_info = init_info
        self.line_edits = {}
        self.setup_ui()

    def setup_ui(self):
        grid_layout = QGridLayout()
        row = 0

        # 定义所有字段的配置（标签文本，init_info属性名，行位置，列位置）
        fields_config = [
            ("数据集名称:", "data_set_name", 0, 0),
            ("采集日期:", "collection_date", 0, 2),
            ("参与者 ID:", "participant_id", 1, 0),
            ("手势类型:", "gesture_type", 1, 2),
            ("采集次数:", "collection_count", 2, 0),
            ("传感器类型:", "sensor_type", 2, 2),
            ("采样频率:", "sampling_frequency", 3, 0),
            ("编码格式:", "encode_format", 3, 2),
        ]

        for label_text, attr_name, r, c in fields_config:
            # 创建标签
            label = QLabel(label_text)
            grid_layout.addWidget(label, r, c)

            # 创建输入框
            input_value = str(getattr(self.init_info, attr_name))  # 获取属性值
            line_edit = QLineEdit(input_value)

            # 保存输入框引用
            self.line_edits[attr_name] = line_edit

            # 为输入框添加修改事件（lambda需捕获当前attr_name）
            line_edit.textChanged.connect(
                lambda text, attr=attr_name: self._on_field_changed(attr, text)
            )

            grid_layout.addWidget(line_edit, r, c + 1)  # 输入框放在标签右侧列

        self.setLayout(grid_layout)

    def _on_field_changed(self, attr_name: str, new_value: str):
        """当字段被修改时触发"""
        # 更新 init_info
        if attr_name == "collection_count":  # 特殊处理整数类型
            setattr(self.init_info, attr_name, int(new_value))
        else:
            setattr(self.init_info, attr_name, new_value)
        msg = "更新："+attr_name
        self.parameterChangedSignal.emit(self.init_info, msg)

    def update_field_value(self, attr_name: str, new_value):
        """外部调用此方法来更新特定字段的值和UI显示"""
        if attr_name in self.line_edits:
            # 更新数据
            if attr_name == "collection_count":
                setattr(self.init_info, attr_name, int(new_value))
            else:
                setattr(self.init_info, attr_name, new_value)

            # 更新UI（临时断开信号连接避免循环触发）
            line_edit = self.line_edits[attr_name]
            line_edit.blockSignals(True)  # 阻止信号
            line_edit.setText(str(new_value))
            line_edit.blockSignals(False)  # 恢复信号

            # 发送更新信号
            msg = "更新：" + attr_name
            self.parameterChangedSignal.emit(self.init_info, msg)

    def increment_collection_count(self):
        """便捷方法：增加采集次数"""
        current_count = self.init_info.collection_count
        self.update_field_value("collection_count", current_count + 1)


