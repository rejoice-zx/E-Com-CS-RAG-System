# -*- coding: utf-8 -*-
"""
日志管理界面
提供日志查看、搜索、清理等功能
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QSplitter, QFileDialog, QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor

from qfluentwidgets import (
    CardWidget, BodyLabel, TitleLabel, SubtitleLabel,
    PushButton, PrimaryPushButton, ComboBox, SpinBox,
    SearchLineEdit, TextEdit, ListWidget, FluentIcon,
    MessageBox, InfoBar, InfoBarPosition, SwitchButton
)

from core.logger import LogManager


class LogViewerPanel(QFrame):
    """日志查看面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.log_manager = LogManager()
        self.current_file = None
        self.auto_refresh = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_log)
        
        self._init_ui()
        self._load_log_files()
    
    def _ensure_valid_font_point_size(self, widget: QWidget) -> None:
        font = widget.font()
        if font.pointSize() > 0:
            return
        base = QApplication.font()
        point_size = base.pointSize()
        if point_size <= 0:
            point_size = 10
        font.setPointSize(point_size)
        widget.setFont(font)
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # 标题行
        title_row = QHBoxLayout()
        title = TitleLabel("📋 日志查看器")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 文件选择
        toolbar.addWidget(BodyLabel("日志文件:"))
        self.file_combo = ComboBox()
        self.file_combo.setMinimumWidth(200)
        self.file_combo.currentTextChanged.connect(self._on_file_changed)
        toolbar.addWidget(self.file_combo)
        
        # 行数选择
        toolbar.addWidget(BodyLabel("显示行数:"))
        self.lines_spin = SpinBox()
        self.lines_spin.setRange(50, 5000)
        self.lines_spin.setValue(200)
        self.lines_spin.valueChanged.connect(self._refresh_log)
        toolbar.addWidget(self.lines_spin)
        
        toolbar.addStretch()
        
        # 自动刷新
        toolbar.addWidget(BodyLabel("自动刷新:"))
        self.auto_refresh_switch = SwitchButton()
        self._ensure_valid_font_point_size(self.auto_refresh_switch)
        self.auto_refresh_switch.checkedChanged.connect(self._toggle_auto_refresh)
        toolbar.addWidget(self.auto_refresh_switch)
        
        # 刷新按钮
        self.refresh_btn = PushButton(FluentIcon.SYNC, "刷新")
        self.refresh_btn.clicked.connect(self._refresh_log)
        toolbar.addWidget(self.refresh_btn)
        
        layout.addLayout(toolbar)
        
        # 搜索栏
        search_row = QHBoxLayout()
        self.search_edit = SearchLineEdit()
        self.search_edit.setPlaceholderText("搜索日志内容...")
        self.search_edit.textChanged.connect(self._on_search)
        search_row.addWidget(self.search_edit)
        
        # 级别过滤
        search_row.addWidget(BodyLabel("级别过滤:"))
        self.level_combo = ComboBox()
        self.level_combo.addItems(["全部", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.level_combo.currentTextChanged.connect(self._filter_by_level)
        search_row.addWidget(self.level_combo)
        
        layout.addLayout(search_row)
        
        # 日志内容
        self.log_text = TextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            TextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.log_text, 1)
        
        # 状态栏
        status_row = QHBoxLayout()
        self.status_label = BodyLabel("就绪")
        self.status_label.setStyleSheet("color: gray;")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        
        self.line_count_label = BodyLabel("0 行")
        self.line_count_label.setStyleSheet("color: gray;")
        status_row.addWidget(self.line_count_label)
        
        layout.addLayout(status_row)
    
    def _load_log_files(self):
        """加载日志文件列表"""
        self.file_combo.clear()
        files = self.log_manager.get_log_files()
        for f in files:
            size_str = self._format_size(f["size"])
            self.file_combo.addItem(f"{f['name']} ({size_str})", f["name"])
        
        if files:
            self.current_file = files[0]["name"]
            self._refresh_log()
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / 1024 / 1024:.1f} MB"
    
    def _on_file_changed(self, text: str):
        """文件选择变化"""
        index = self.file_combo.currentIndex()
        if index >= 0:
            self.current_file = self.file_combo.itemData(index)
            self._refresh_log()
    
    def _refresh_log(self):
        """刷新日志内容"""
        if not self.current_file:
            return
        
        lines = self.lines_spin.value()
        content = self.log_manager.read_log(self.current_file, lines)
        
        # 保存当前滚动位置
        scrollbar = self.log_text.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        
        self.log_text.setPlainText(content)
        self._highlight_log_levels()
        
        # 如果之前在底部，保持在底部
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        
        # 更新状态
        line_count = content.count('\n')
        self.line_count_label.setText(f"{line_count} 行")
        self.status_label.setText(f"已加载: {self.current_file}")
    
    def _highlight_log_levels(self):
        """高亮日志级别"""
        cursor = self.log_text.textCursor()
        
        # 定义颜色
        colors = {
            "DEBUG": QColor("#6A9955"),
            "INFO": QColor("#4FC1FF"),
            "WARNING": QColor("#DCDCAA"),
            "ERROR": QColor("#F14C4C"),
            "CRITICAL": QColor("#FF0000"),
        }
        
        text = self.log_text.toPlainText()
        
        for level, color in colors.items():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            
            start = 0
            while True:
                pos = text.find(f"| {level}", start)
                if pos == -1:
                    break
                
                cursor.setPosition(pos)
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(level) + 2)
                cursor.mergeCharFormat(fmt)
                start = pos + 1
    
    def _on_search(self, text: str):
        """搜索日志"""
        if not text:
            self._refresh_log()
            return
        
        content = self.log_text.toPlainText()
        lines = content.split('\n')
        filtered = [line for line in lines if text.lower() in line.lower()]
        
        self.log_text.setPlainText('\n'.join(filtered))
        self.line_count_label.setText(f"{len(filtered)} 行 (已过滤)")
    
    def _filter_by_level(self, level: str):
        """按级别过滤"""
        if level == "全部":
            self._refresh_log()
            return
        
        if not self.current_file:
            return
        
        lines = self.lines_spin.value()
        content = self.log_manager.read_log(self.current_file, lines)
        lines_list = content.split('\n')
        filtered = [line for line in lines_list if f"| {level}" in line]
        
        self.log_text.setPlainText('\n'.join(filtered))
        self.line_count_label.setText(f"{len(filtered)} 行 ({level})")
    
    def _toggle_auto_refresh(self, checked: bool):
        """切换自动刷新"""
        self.auto_refresh = checked
        if checked:
            self.refresh_timer.start(3000)  # 3秒刷新一次
            self.status_label.setText("自动刷新已启用 (3秒)")
        else:
            self.refresh_timer.stop()
            self.status_label.setText("自动刷新已停止")


class LogManagePanel(QFrame):
    """日志管理面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        
        self.log_manager = LogManager()
        self._init_ui()
        self._refresh_file_list()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # 标题
        title = SubtitleLabel("📁 日志文件")
        layout.addWidget(title)
        
        # 文件列表
        self.file_list = ListWidget()
        self.file_list.setStyleSheet("""
            ListWidget {
                border: 1px solid rgba(0,0,0,0.1);
                border-radius: 4px;
            }
            ListWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(0,0,0,0.05);
            }
            ListWidget::item:selected {
                background-color: rgba(0, 120, 212, 0.1);
            }
        """)
        layout.addWidget(self.file_list, 1)
        
        # 操作按钮
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)
        
        self.export_btn = PushButton(FluentIcon.DOWNLOAD, "导出日志")
        self.export_btn.clicked.connect(self._export_log)
        btn_layout.addWidget(self.export_btn)
        
        self.clear_btn = PushButton(FluentIcon.DELETE, "清理旧日志")
        self.clear_btn.clicked.connect(self._clear_old_logs)
        btn_layout.addWidget(self.clear_btn)
        
        self.refresh_btn = PushButton(FluentIcon.SYNC, "刷新列表")
        self.refresh_btn.clicked.connect(self._refresh_file_list)
        btn_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(btn_layout)
        
        # 设置卡片
        settings_card = CardWidget()
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(8)
        
        settings_title = BodyLabel("⚙️ 日志设置")
        settings_title.setStyleSheet("font-weight: bold;")
        settings_layout.addWidget(settings_title)
        
        # 控制台日志级别
        level_row = QHBoxLayout()
        level_row.addWidget(BodyLabel("控制台级别:"))
        self.console_level = ComboBox()
        self.console_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.console_level.setCurrentText("INFO")
        self.console_level.currentTextChanged.connect(self._on_console_level_changed)
        level_row.addWidget(self.console_level)
        settings_layout.addLayout(level_row)
        
        # 文件日志级别
        file_level_row = QHBoxLayout()
        file_level_row.addWidget(BodyLabel("文件级别:"))
        self.file_level = ComboBox()
        self.file_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.file_level.setCurrentText("DEBUG")
        self.file_level.currentTextChanged.connect(self._on_file_level_changed)
        file_level_row.addWidget(self.file_level)
        settings_layout.addLayout(file_level_row)
        
        layout.addWidget(settings_card)
        
        # 统计信息
        self.stats_label = BodyLabel("统计: -")
        self.stats_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.stats_label)
    
    def _refresh_file_list(self):
        """刷新文件列表"""
        self.file_list.clear()
        files = self.log_manager.get_log_files()
        
        total_size = 0
        for f in files:
            size_str = self._format_size(f["size"])
            self.file_list.addItem(f"📄 {f['name']}\n   {size_str} | {f['modified']}")
            total_size += f["size"]
        
        self.stats_label.setText(f"共 {len(files)} 个文件，总大小: {self._format_size(total_size)}")
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / 1024 / 1024:.1f} MB"
    
    def _export_log(self):
        """导出日志"""
        files = self.log_manager.get_log_files()
        if not files:
            InfoBar.warning(
                title="无日志文件",
                content="没有可导出的日志文件",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        # 选择保存位置
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "logs_export.txt", "文本文件 (*.txt);;所有文件 (*)"
        )
        
        if not save_path:
            return
        
        try:
            # 合并所有日志
            content = []
            for f in files:
                content.append(f"{'='*60}")
                content.append(f"文件: {f['name']}")
                content.append(f"{'='*60}")
                content.append(self.log_manager.read_log(f['name'], 10000))
                content.append("\n")
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content))
            
            InfoBar.success(
                title="导出成功",
                content=f"日志已导出到: {save_path}",
                parent=self,
                position=InfoBarPosition.TOP
            )
        except Exception as e:
            InfoBar.error(
                title="导出失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def _clear_old_logs(self):
        """清理旧日志"""
        box = MessageBox(
            "清理旧日志",
            "确定要清理7天前的日志文件吗？\n此操作不可恢复。",
            self
        )
        
        if box.exec():
            deleted = self.log_manager.clear_logs(keep_days=7)
            self._refresh_file_list()
            
            InfoBar.success(
                title="清理完成",
                content=f"已删除 {deleted} 个旧日志文件",
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def _on_console_level_changed(self, level: str):
        """控制台日志级别变化"""
        self.log_manager.set_level(level, "console")
        InfoBar.info(
            title="设置已更新",
            content=f"控制台日志级别: {level}",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=1500
        )
    
    def _on_file_level_changed(self, level: str):
        """文件日志级别变化"""
        self.log_manager.set_level(level, "file")
        InfoBar.info(
            title="设置已更新",
            content=f"文件日志级别: {level}",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=1500
        )


class LogInterface(QWidget):
    """日志管理界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("log_interface")
        self._init_ui()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 日志查看面板
        self.viewer_panel = LogViewerPanel()
        layout.addWidget(self.viewer_panel, 1)
        
        # 日志管理面板
        self.manage_panel = LogManagePanel()
        layout.addWidget(self.manage_panel)
    
    def refresh(self):
        """刷新界面"""
        self.viewer_panel._load_log_files()
        self.manage_panel._refresh_file_list()
