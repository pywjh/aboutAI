import sys
import os
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QTextEdit, QFileDialog, QProgressBar, QComboBox,
                             QFrame, QScrollArea, QGridLayout, QGroupBox,
                             QSizePolicy, QDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap
from video_note_generator import VideoNoteGenerator

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # 禁用SSL警告

BUTTON_STYLE = """
    QPushButton {
        background-color: #FF1493;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 8px 15px;
        font-weight: bold;
        font-size: 13px;
    }
    QPushButton:hover {
        background-color: #FF69B4;
        border: 2px solid #00FFFF;
    }
    QPushButton:pressed {
        background-color: #FF1493;
    }
"""


class CyberpunkLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet("background-color: #FF1493;")
        self.setFixedHeight(2)


class ImageDownloader(QThread):
    downloaded = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.save_dir = os.path.join(os.path.dirname(__file__), "temp_images")
        os.makedirs(self.save_dir, exist_ok=True)

    def run(self):
        try:
            # 生成文件名
            filename = os.path.join(self.save_dir, f"image_{hash(self.url)}.jpg")

            # 配置重试策略
            retry_strategy = Retry(
                total=3,  # 总重试次数
                backoff_factor=1,  # 重试间隔
                status_forcelist=[500, 502, 503, 504]  # 需要重试的HTTP状态码
            )

            # 创建会话
            session = requests.Session()
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }

            # 发送请求
            response = session.get(
                self.url,
                headers=headers,
                verify=False,  # 禁用SSL验证
                timeout=30,
                stream=True  # 流式下载
            )
            response.raise_for_status()

            # 检查内容类型
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                raise ValueError(f"非图片内容: {content_type}")

            # 流式写入文件
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # 验证文件
            if os.path.getsize(filename) == 0:
                raise ValueError("下载的文件大小为0")

            self.downloaded.emit(filename, self.url)

        except requests.exceptions.SSLError as e:
            error_msg = f"SSL错误: {str(e)}"
            print(f"Error: {error_msg}")
            self.error.emit(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f"请求错误: {str(e)}"
            print(f"Error: {error_msg}")
            self.error.emit(error_msg)

        except Exception as e:
            error_msg = f"下载错误: {str(e)}"
            print(f"Error: {error_msg}")
            self.error.emit(error_msg)

        finally:
            session.close()


class ProcessThread(QThread):
    progress = pyqtSignal(str)  # 用于显示进度日志
    content_ready = pyqtSignal(str)  # 用于显示API生成的内容
    finished = pyqtSignal(bool, list)

    def __init__(self, generator: VideoNoteGenerator, source: str):
        super().__init__()
        self.generator = generator
        self.source = source

    def run(self):
        try:
            def print_redirect(msg: str):
                # 检查是否是API返回的内容
                if "API返回内容：" in msg:
                    # 提取API返回的内容部分
                    content = msg.split("API返回内容：", 1)[1].strip()
                    self.content_ready.emit(content)
                    return

                # 处理进度日志
                if "正在处理视频" in msg:
                    msg = "📹 " + msg
                elif "正在转录音频" in msg:
                    msg = "🎙️ " + msg
                elif "正在整理长文版本" in msg:
                    msg = "📝 " + msg
                elif "正在生成小红书版本" in msg:
                    msg = "📱 " + msg
                elif "成功" in msg or "完成" in msg:
                    msg = "✅ " + msg
                elif "失败" in msg or "错误" in msg:
                    msg = "❌ " + msg
                elif "警告" in msg:
                    msg = "⚠️ " + msg
                elif "下载" in msg:
                    msg = "⬇️ " + msg

                self.progress.emit(str(msg))

            # 保存原始print函数
            original_print = print
            import builtins
            builtins.print = print_redirect

            # 处理视频
            result_files = self.generator.process_video(self.source)

            # 恢复原始print函数
            builtins.print = original_print

            # 检查处理结果
            if result_files and len(result_files) == 3:
                self.finished.emit(True, result_files)
            else:
                self.progress.emit("⚠️ 未能生成完整的笔记文件")
                self.finished.emit(False, result_files or [])

        except Exception as e:
            self.progress.emit(f"❌ 错误: {str(e)}")
            self.finished.emit(False, [])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("小红书笔记生成器")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(CYBERPUNK_STYLE)

        # 初始化变量
        self.file_filter = "视频文件 (*.mp4 *.avi *.mov *.mkv *.flv)"
        self.generator = VideoNoteGenerator()
        self.process_thread = None
        self.image_downloaders = []

        # 设置主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setSpacing(15)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        # 初始化UI
        self._setup_ui()

    def _setup_ui(self):
        """设置UI界面"""
        # 添加标题
        title_label = QLabel("🌆 小红书笔记生成器 🌆")
        title_label.setStyleSheet("""
            font-size: 24px;
            color: #FF1493;
            padding: 10px;
            border: 2px solid #FF1493;
            border-radius: 10px;
            background-color: #2A2A3E;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(title_label)
        self.main_layout.addWidget(CyberpunkLine())

        # 添加输入区域
        input_widget = QWidget()
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)

        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("选择视频文件...")
        self.input_path.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border: 2px solid #FF1493;
                border-radius: 5px;
                background-color: #2A2A3E;
                color: #FFFFFF;
            }
        """)
        input_layout.addWidget(self.input_path)

        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet(BUTTON_STYLE)
        browse_btn.clicked.connect(self.browse_file)
        input_layout.addWidget(browse_btn)

        self.main_layout.addWidget(input_widget)

        # 添加分割线
        self.main_layout.addWidget(CyberpunkLine())

        # 添加显示区域
        display_widget = QWidget()
        display_layout = QHBoxLayout(display_widget)

        # 左侧进度日志区域
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 10, 0)

        log_label = QLabel("📟 处理日志")
        log_layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2A2A3E;
                border: 2px solid #FF1493;
                border-radius: 5px;
                padding: 5px;
                color: #00FFFF;
                font-size: 13px;
            }
        """)
        log_layout.addWidget(self.log_text)

        # 右侧内容区域
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 0, 0, 0)

        # 标题区域 - 固定高度
        title_group = QGroupBox("🎯 标题")
        title_layout = QVBoxLayout(title_group)
        self.title_text = QTextEdit()
        self.title_text.setReadOnly(True)
        self.title_text.setFixedHeight(60)  # 使用固定高度
        self.title_text.setStyleSheet("""
            QTextEdit {
                background-color: #2A2A3E;
                border: 2px solid #FF1493;
                border-radius: 5px;
                color: #FF1493;
                font-size: 15px;
                font-weight: bold;
                padding: 5px;
            }
        """)
        title_layout.addWidget(self.title_text)
        content_layout.addWidget(title_group, 0)  # stretch factor 为 0，不伸展

        # 图片预览区域 - 统一样式
        preview_group = QGroupBox("🖼️ 配图")
        preview_layout = QVBoxLayout(preview_group)

        # 创建配图容器和滚动区域
        extra_images_container = QWidget()
        extra_images_container.setStyleSheet("""
            QWidget {
                background-color: #2A2A3E;
            }
        """)
        self.extra_images_layout = QHBoxLayout(extra_images_container)
        self.extra_images_layout.setSpacing(10)
        self.extra_images_layout.setContentsMargins(5, 5, 5, 5)

        # 创建滚动区域 - 统一样式
        scroll_area = QScrollArea()
        scroll_area.setWidget(extra_images_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMinimumHeight(200)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #2A2A3E;
                border: 2px solid #FF1493;
                border-radius: 5px;
                padding: 5px;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #2A2A3E;
            }
            QScrollBar:horizontal {
                border: none;
                background: #1A1A2E;
                height: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: #FF1493;
                border-radius: 5px;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        preview_layout.addWidget(scroll_area)
        content_layout.addWidget(preview_group, 0)  # stretch factor 为 0，不伸展

        # 正文内容区域 - 自适应高度
        content_group = QGroupBox("📝 内容")
        content_inner_layout = QVBoxLayout(content_group)
        self.content_text = QTextEdit()
        self.content_text.setReadOnly(True)

        # 设置尺寸策略为扩展
        size_policy = self.content_text.sizePolicy()
        size_policy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        size_policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        self.content_text.setSizePolicy(size_policy)

        self.content_text.setStyleSheet("""
            QTextEdit {
                background-color: #2A2A3E;
                border: 2px solid #FF1493;
                border-radius: 5px;
                color: #FFFFFF;
                font-size: 13px;
                padding: 5px;
            }
        """)
        content_inner_layout.addWidget(self.content_text)
        content_layout.addWidget(content_group, 1)  # stretch factor 为 1，会伸展

        # 标签区域 - 固定高度
        tags_group = QGroupBox("🏷️ 标签")
        tags_layout = QVBoxLayout(tags_group)
        self.tags_text = QTextEdit()
        self.tags_text.setReadOnly(True)
        self.tags_text.setFixedHeight(60)  # 使用固定高度
        self.tags_text.setStyleSheet("""
            QTextEdit {
                background-color: #2A2A3E;
                border: 2px solid #FF1493;
                border-radius: 5px;
                color: #00FF00;
                font-size: 13px;
                padding: 5px;
            }
        """)
        tags_layout.addWidget(self.tags_text)
        content_layout.addWidget(tags_group, 0)  # stretch factor 为 0，不伸展

        # 设置左右比例为3:7
        display_layout.addWidget(log_widget, 3)
        display_layout.addWidget(content_widget, 7)

        self.main_layout.addWidget(display_widget)

        # 添加进度条和处理按钮
        process_widget = QWidget()
        process_layout = QHBoxLayout(process_widget)
        process_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #FF1493;
                border-radius: 5px;
                text-align: center;
                background-color: #2A2A3E;
            }
            QProgressBar::chunk {
                background-color: #FF1493;
            }
        """)
        process_layout.addWidget(self.progress_bar)

        self.run_btn = QPushButton("运行")
        self.run_btn.setStyleSheet(BUTTON_STYLE)
        self.run_btn.clicked.connect(self.start_processing)
        process_layout.addWidget(self.run_btn)

        self.main_layout.addWidget(process_widget)

    def start_processing(self):
        """开始处理"""
        # 获取输入源
        source = self.input_path.text().strip()
        if not source:
            self.log_text.append("❌ 请先选择输入源")
            return

        # 清空之前的内容
        self.log_text.clear()
        self.title_text.clear()
        self.content_text.clear()
        self.tags_text.clear()

        # 清空配图区域
        while self.extra_images_layout.count():
            item = self.extra_images_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 禁用运行按钮
        self.run_btn.setEnabled(False)

        # 设置进度条
        self.progress_bar.setMaximum(0)
        self.progress_bar.setValue(0)

        # 开始处理
        self.process_thread = ProcessThread(self.generator, source)
        self.process_thread.progress.connect(self.update_progress)
        self.process_thread.finished.connect(self.processing_finished)
        self.process_thread.start()

    def handle_image_downloaded(self, image_path: str, original_url: str):
        """处理下载完成的图片"""
        try:
            self.log_text.append(f"\n⏳ 正在处理图片: {original_url}")

            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                self.log_text.append(f"❌ 无法加载图片: {image_path}")
                return

            # 统一的图片显示逻辑
            image_label = QLabel()
            image_label.setFixedSize(180, 180)
            scaled_pixmap = pixmap.scaled(
                170, 170,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            image_label.setPixmap(scaled_pixmap)
            image_label.setStyleSheet("""
                QLabel {
                    background-color: #2A2A3E;
                    padding: 5px;
                    border: 2px solid #FF1493;
                    border-radius: 5px;
                }
                QLabel:hover {
                    border: 2px solid #00FFFF;
                }
            """)

            # 设置鼠标样式
            image_label.setCursor(Qt.CursorShape.PointingHandCursor)

            # 存储原始图片路径
            image_label.setProperty("image_path", image_path)

            # 添加点击事件
            def show_preview():
                dialog = ImagePreviewDialog(image_path, self)
                dialog.exec()

            # 使Label可以接收鼠标点击事件
            image_label.setMouseTracking(True)
            image_label.mousePressEvent = lambda e: show_preview()

            self.extra_images_layout.addWidget(image_label)
            self.log_text.append(f"✅ 图片已加载并显示: {image_path}")
        except Exception as e:
            self.log_text.append(f"❌ 处理图片时出错: {str(e)}")
            import traceback
            self.log_text.append(f"详细错误信息:\n{traceback.format_exc()}")

    def handle_download_error(self, error_message: str):
        """处理下载错误"""
        self.log_text.append(f"❌ {error_message}")
        # 添加更多错误信息
        import traceback
        self.log_text.append(f"详细错误信息:\n{traceback.format_exc()}")

    def update_progress(self, msg: str):
        """更新进度"""
        self.log_text.append(msg)

    def processing_finished(self, success: bool, files: list):
        """处理完成"""
        self.run_btn.setEnabled(True)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100)

        if success and files:
            self.log_text.append("\n✅ 处理完成!")
            try:
                xiaohongshu_file = [f for f in files if f.endswith('_xiaohongshu.md')][0]
                with open(xiaohongshu_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 1. 修改标题提取逻辑
                title_match = re.search(r'^##\s*(.*?)(?:\n|$)', content, re.MULTILINE)
                if title_match:
                    title = title_match.group(1).strip()
                    self.title_text.setText(title)
                    self.log_text.append("\n✅ 提取到标题")

                # 2. 提取正文内容
                # 去掉标题
                content_without_title = re.sub(r'^#.*?\n', '', content, 1)
                # 去掉图片链接
                content_without_images = re.sub(r'!\[.*?\]\(.*?\)\n?', '', content_without_title)
                # 去掉标签部分
                main_content = re.split(r'\n---\n', content_without_images)[0].strip()
                # 去掉多余的空行
                main_content = re.sub(r'\n{3,}', '\n\n', main_content)
                self.content_text.setText(main_content)

                # 3. 提取标签
                extractor = TagExtractor(content)
                tags, debug_info = extractor.extract()

                # 输出调试信息
                self.log_text.append("\n📑 标签提取过程:")
                for info in debug_info:
                    self.log_text.append(f"ℹ️ {info}")

                if tags:
                    # 过滤掉空标签并去重
                    tags = list(filter(None, tags))
                    tags = list(dict.fromkeys(tags))  # 去重保持顺序

                    # 显示标签
                    self.tags_text.setText(' '.join([f"#{tag}" for tag in tags]))
                    self.log_text.append(f"\n✅ 最终提取到{len(tags)}个标签")
                    self.log_text.append(f"标签内容: {' '.join([f'#{tag}' for tag in tags])}")
                else:
                    self.log_text.append("\n⚠️ 所有策略都未能找到有效标签")

                # 4. 提取图片链接并下载
                image_links = re.findall(r'!\[.*?\]\((.*?)\)', content)
                if image_links:
                    self.log_text.append(f"\n📥 开始下载{len(image_links)}张图片...")
                    for i, url in enumerate(image_links):
                        self.log_text.append(f"\n🔄 正在下载第{i + 1}张图片: {url}")
                        downloader = ImageDownloader(url)
                        downloader.downloaded.connect(self.handle_image_downloaded)
                        downloader.error.connect(self.handle_download_error)
                        downloader.start()
                        self.image_downloaders.append(downloader)

            except Exception as e:
                self.log_text.append(f"\n❌ 处理文件时出错: {str(e)}")
                import traceback
                self.log_text.append(f"\n{traceback.format_exc()}")
        else:
            self.log_text.append("\n❌ 处理失败")

    def browse_file(self):
        """浏览文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            "",
            self.file_filter
        )
        if file_path:
            self.input_path.setText(file_path)


# 赛博朋克风格
CYBERPUNK_STYLE = """
QMainWindow {
    background-color: #1A1A2E;
}

QWidget {
    color: #00FFFF;
    font-family: 'Segoe UI', 'Microsoft YaHei';
}

QLabel {
    color: #FF1493;
    font-size: 14px;
    font-weight: bold;
}

QLineEdit {
    background-color: #2A2A3E;
    border: 2px solid #FF1493;
    border-radius: 5px;
    padding: 5px;
    color: #00FFFF;
    font-size: 13px;
}

QLineEdit:focus {
    border-color: #00FFFF;
}

QPushButton {
    background-color: #FF1493;
    color: white;
    border: none;
    border-radius: 5px;
    padding: 8px 15px;
    font-weight: bold;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #FF69B4;
    border: 2px solid #00FFFF;
}

QPushButton:pressed {
    background-color: #FF1493;
}

QComboBox {
    background-color: #2A2A3E;
    border: 2px solid #FF1493;
    border-radius: 5px;
    padding: 5px;
    color: #00FFFF;
    font-size: 13px;
}

QComboBox::drop-down {
    border: none;
}

QComboBox::down-arrow {
    image: url(down_arrow.png);
    width: 12px;
    height: 12px;
}

QProgressBar {
    border: 2px solid #FF1493;
    border-radius: 5px;
    text-align: center;
    background-color: #2A2A3E;
}

QProgressBar::chunk {
    background-color: #00FFFF;
}

QTextEdit {
    background-color: #2A2A3E;
    border: 2px solid #FF1493;
    border-radius: 5px;
    padding: 5px;
    color: #00FFFF;
    font-size: 13px;
}
"""


# 添加图片预览对话框类
class ImagePreviewDialog(QDialog):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("图片预览")
        self.setStyleSheet("""
            QDialog {
                background-color: #1A1A2E;
            }
        """)

        # 设置对话框大小为屏幕大小的80%
        screen = QApplication.primaryScreen().size()
        self.resize(int(screen.width() * 0.8), int(screen.height() * 0.8))

        # 创建布局
        layout = QVBoxLayout(self)

        # 创建图片标签
        image_label = QLabel()
        pixmap = QPixmap(image_path)

        # 等比例缩放图片以适应对话框大小
        scaled_pixmap = pixmap.scaled(
            int(self.width() * 0.9),  # 转换为整数
            int(self.height() * 0.9),  # 转换为整数
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        image_label.setPixmap(scaled_pixmap)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(image_label)

        # 添加关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(BUTTON_STYLE)
        close_btn.clicked.connect(self.close)
        close_btn.setFixedWidth(100)

        # 创建按钮容器使其居中
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()

        layout.addWidget(btn_container)


class TagExtractor:
    def __init__(self, content: str):
        self.content = content
        self.debug_info = []

    def extract(self):
        """尝试所有策略提取标签"""
        # 按优先级尝试不同的提取策略
        extractors = [
            self._extract_grouped_tags,
            self._extract_single_line_tags,
            self._extract_multiline_tags,
            self._extract_simple_tags
        ]

        for extractor in extractors:
            tags = extractor()
            if tags:
                return tags, self.debug_info

        return [], self.debug_info

    def _extract_grouped_tags(self):
        """策略1：提取分组格式的标签 (# 组名 # 标签1 # 标签2)"""
        try:
            tag_section = re.search(r'---\n(.*?)$', self.content, re.DOTALL)
            if not tag_section:
                self.debug_info.append("未找到标签部分(---)，尝试下一个策略")
                return []

            tag_content = tag_section.group(1).strip()
            tags = []

            for line in tag_content.split('\n'):
                if line.strip():
                    line_tags = re.findall(r'#\s*([^#\n]+?)(?=\s*#|$)', line)
                    if line_tags:
                        # 跳过分组名称（第一个标签）
                        tags.extend([tag.strip() for tag in line_tags[1:]])

            if tags:
                self.debug_info.append(f"使用分组格式策略成功提取到{len(tags)}个标签")
                return tags

            self.debug_info.append("分组格式策略未找到标签，尝试下一个策略")
            return []
        except Exception as e:
            self.debug_info.append(f"分组格式策略出错: {str(e)}")
            return []

    def _extract_single_line_tags(self):
        """策略2：提取单行格式的标签 (# 标签1 # 标签2 # 标签3)"""
        try:
            # 查找以#开头的行
            tag_lines = re.findall(r'^(#[^#\n]+(?:\s*#[^#\n]+)*)\s*$', self.content, re.MULTILINE)
            if not tag_lines:
                self.debug_info.append("未找到单行标签，尝试下一个策略")
                return []

            # 从最后一行提取标签（通常标签在文末）
            last_tag_line = tag_lines[-1]
            tags = re.findall(r'#\s*([^#\n]+?)(?=\s*#|$)', last_tag_line)

            if tags:
                tags = [tag.strip() for tag in tags]
                self.debug_info.append(f"使用单行格式策略成功提取到{len(tags)}个标签")
                return tags

            self.debug_info.append("单行格式策略未找到标签，尝试下一个策略")
            return []
        except Exception as e:
            self.debug_info.append(f"单行格式策略出错: {str(e)}")
            return []

    def _extract_multiline_tags(self):
        """策略3：提取多行格式的标签（每行一个标签）"""
        try:
            # 查找连续的标签行
            tag_section = re.search(r'(?:^|\n)((?:#[^\n]+\n?)+)', self.content)
            if not tag_section:
                self.debug_info.append("未找到多行标签，尝试下一个策略")
                return []

            tag_content = tag_section.group(1)
            tags = re.findall(r'#\s*([^#\n]+?)(?=\s*$)', tag_content, re.MULTILINE)

            if tags:
                tags = [tag.strip() for tag in tags]
                self.debug_info.append(f"使用多行格式策略成功提取到{len(tags)}个标签")
                return tags

            self.debug_info.append("多行格式策略未找到标签，尝试下一个策略")
            return []
        except Exception as e:
            self.debug_info.append(f"多行格式策略出错: {str(e)}")
            return []

    def _extract_simple_tags(self):
        """策略4：简单提取所有#后面的内容"""
        try:
            # 直接匹配所有#后面的内容
            tags = re.findall(r'#\s*([^#\n]+?)(?=\s*(?:#|$))', self.content)

            if tags:
                tags = [tag.strip() for tag in tags]
                # 过滤掉可能的非标签内容
                tags = [tag for tag in tags if len(tag) < 20 and not re.search(r'[.。,，:：]', tag)]
                self.debug_info.append(f"使用简单格式策略成功提取到{len(tags)}个标签")
                return tags

            self.debug_info.append("简单格式策略未找到标签")
            return []
        except Exception as e:
            self.debug_info.append(f"简单格式策略出错: {str(e)}")
            return []


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
