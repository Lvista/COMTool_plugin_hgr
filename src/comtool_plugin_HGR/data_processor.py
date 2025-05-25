import struct
from PyQt5.QtCore import QObject, pyqtSignal
from typing import Tuple, Optional
# 移除未使用的导入
# from typing import List

class FloatFrameParser(QObject):
    """
    解析格式：[0xAA, uint8, float32, float32, float32, 0xEE]
    """
    # 调整信号参数数量，去掉多余的参数
    frame_parsed = pyqtSignal(int, float, float, float)  # (uint8, float1, float2, float3)
    invalid_frame = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self.FRAME_HEAD = 0xAA
        self.FRAME_TAIL = 0xEE
        # 修正格式字符串，使用 'B' 表示无符号字节
        self.FRAME_FORMAT = '=Bfff'  # uint8 + 3个float32 (小端序)
        self._frame_size = struct.calcsize(self.FRAME_FORMAT) + 2  # 加上头和尾

    def parse_frame(self, raw_data: bytes) \
            -> Optional[Tuple[
                int,
                float,
                float,
                float,
            ]]:
        """解析数据帧"""
        # 基础检查
        if len(raw_data) != self._frame_size:
            return None
        if raw_data[0] != self.FRAME_HEAD or raw_data[-1] != self.FRAME_TAIL:
            return None

        try:
            # 提取数据部分 (去掉头尾)
            data_part = raw_data[1:-1]
            # 解析二进制数据，调整解包参数数量
            uint8_val, float1, float2, float3 = struct.unpack(self.FRAME_FORMAT, data_part)
            return uint8_val, float1, float2, float3
        except struct.error:
            return None

    def process_raw_data(self, raw_data: bytes):
        """处理原始数据并发射信号"""
        result = self.parse_frame(raw_data)
        if result:
            self.frame_parsed.emit(*result)
        else:
            self.invalid_frame.emit(raw_data)


# 使用示例
if __name__ == "__main__":
    # 测试帧构造 (AA, uint8=5, 1.23, 4.56, 7.89, EE)
    test_frame = bytes([0xAA]) + struct.pack('=Bfff', 5, 1.23, 4.56, 7.89) + bytes([0xEE])

    parser = FloatFrameParser()

    # 连接信号，调整参数数量
    parser.frame_parsed.connect(lambda u, f1, f2, f3:
                                print(f"解析成功: uint8={u}, floats=({f1}, {f2}, {f3})"))
    parser.invalid_frame.connect(lambda d:
                                 print(f"无效帧: {d.hex(' ')}"))

    # 测试解析
    parser.process_raw_data(test_frame)  # 正常帧
    parser.process_raw_data(b'\xAA\x01\x02\xEE')  # 错误帧
