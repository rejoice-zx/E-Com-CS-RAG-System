# -*- coding: utf-8 -*-
"""
性能监控界面
提供性能指标查看、图表展示、报告导出等功能
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QGridLayout, QFileDialog, QHeaderView, QApplication
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from qfluentwidgets import (
    CardWidget, BodyLabel, TitleLabel, SubtitleLabel,
    PushButton, PrimaryPushButton, ComboBox, 
    TableWidget, FluentIcon, InfoBar, InfoBarPosition,
    SwitchButton, ProgressBar
)

from core.performance import PerformanceMonitor


class MetricCard(CardWidget):
    """单个指标卡片"""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        # 标题
        self.title_label = BodyLabel(title)
        self.title_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.title_label)
        
        # 主要数值
        self.value_label = TitleLabel("--")
        self.value_label.setStyleSheet("font-size: 28px; font-weight: bold;")
        layout.addWidget(self.value_label)
        
        # 副标题/描述
        self.desc_label = BodyLabel("")
        self.desc_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.desc_label)
        
        layout.addStretch()
    
    def set_value(self, value: str, desc: str = ""):
        """设置数值"""
        self.value_label.setText(value)
        self.desc_label.setText(desc)


class PerformanceInterface(QWidget):
    """性能监控界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("performance_interface")
        
        self.monitor = PerformanceMonitor()
        self.auto_refresh = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data)
        
        self._init_ui()
        self._refresh_data()
    
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
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # 标题栏
        header = QHBoxLayout()
        title = TitleLabel("📊 性能监控")
        header.addWidget(title)
        header.addStretch()
        
        # 自动刷新
        header.addWidget(BodyLabel("自动刷新:"))
        self.auto_refresh_switch = SwitchButton()
        self._ensure_valid_font_point_size(self.auto_refresh_switch)
        self.auto_refresh_switch.checkedChanged.connect(self._toggle_auto_refresh)
        header.addWidget(self.auto_refresh_switch)
        
        # 刷新按钮
        self.refresh_btn = PushButton(FluentIcon.SYNC, "刷新")
        self.refresh_btn.clicked.connect(self._refresh_data)
        header.addWidget(self.refresh_btn)
        
        # 导出按钮
        self.export_btn = PushButton(FluentIcon.DOWNLOAD, "导出报告")
        self.export_btn.clicked.connect(self._export_report)
        header.addWidget(self.export_btn)
        
        # 清空按钮
        self.clear_btn = PushButton(FluentIcon.DELETE, "清空数据")
        self.clear_btn.clicked.connect(self._clear_data)
        header.addWidget(self.clear_btn)
        
        layout.addLayout(header)
        
        # 概览卡片
        overview_layout = QHBoxLayout()
        overview_layout.setSpacing(12)
        
        self.uptime_card = MetricCard("运行时长")
        overview_layout.addWidget(self.uptime_card)
        
        self.requests_card = MetricCard("总请求数")
        overview_layout.addWidget(self.requests_card)
        
        self.success_card = MetricCard("总体成功率")
        overview_layout.addWidget(self.success_card)
        
        self.avg_time_card = MetricCard("平均响应时间")
        overview_layout.addWidget(self.avg_time_card)
        
        layout.addLayout(overview_layout)
        
        # 详细指标表格
        table_card = CardWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)
        
        table_header = QHBoxLayout()
        table_header.addWidget(SubtitleLabel("📈 各指标详情"))
        table_header.addStretch()
        
        # 统计范围选择
        table_header.addWidget(BodyLabel("统计范围:"))
        self.range_combo = ComboBox()
        self.range_combo.addItems(["最近100条", "最近500条", "全部"])
        self.range_combo.currentTextChanged.connect(self._refresh_data)
        table_header.addWidget(self.range_combo)
        
        table_layout.addLayout(table_header)
        
        # 表格
        self.metrics_table = TableWidget()
        self.metrics_table.setColumnCount(8)
        self.metrics_table.setHorizontalHeaderLabels([
            "指标名称", "请求数", "成功率", "平均耗时", 
            "最小耗时", "最大耗时", "P50", "P95"
        ])
        self.metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.metrics_table.setEditTriggers(TableWidget.NoEditTriggers)
        self.metrics_table.setSelectionBehavior(TableWidget.SelectRows)
        self.metrics_table.setStyleSheet("""
            TableWidget {
                border: 1px solid rgba(0,0,0,0.1);
                border-radius: 4px;
            }
        """)
        table_layout.addWidget(self.metrics_table)
        
        layout.addWidget(table_card, 1)
        
        # 状态栏
        status_layout = QHBoxLayout()
        self.status_label = BodyLabel("就绪")
        self.status_label.setStyleSheet("color: gray;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        
        self.last_update_label = BodyLabel("")
        self.last_update_label.setStyleSheet("color: gray;")
        status_layout.addWidget(self.last_update_label)
        
        layout.addLayout(status_layout)
    
    def _get_stats_range(self) -> int:
        """获取统计范围"""
        text = self.range_combo.currentText()
        if text == "最近100条":
            return 100
        elif text == "最近500条":
            return 500
        return None  # 全部
    
    def _refresh_data(self):
        """刷新数据"""
        last_n = self._get_stats_range()
        summary = self.monitor.get_summary()
        stats = self.monitor.get_all_stats(last_n)
        
        # 更新概览卡片
        self.uptime_card.set_value(
            summary["uptime_formatted"],
            f"共 {summary['uptime_seconds']:.0f} 秒"
        )
        
        self.requests_card.set_value(
            str(summary["total_requests"]),
            "次操作"
        )
        
        success_rate = summary["overall_success_rate"]
        self.success_card.set_value(
            f"{success_rate:.1%}",
            "成功" if success_rate >= 0.95 else "需关注" if success_rate >= 0.8 else "异常"
        )
        
        # 计算平均响应时间
        total_duration = 0
        total_count = 0
        for s in stats.values():
            if s["count"] > 0:
                total_duration += s["avg_duration"] * s["count"]
                total_count += s["count"]
        
        avg_time = total_duration / total_count if total_count > 0 else 0
        self.avg_time_card.set_value(
            f"{avg_time*1000:.0f}ms",
            "快速" if avg_time < 0.5 else "正常" if avg_time < 2 else "较慢"
        )
        
        # 更新表格
        self._update_table(stats)
        
        # 更新状态
        from datetime import datetime
        self.last_update_label.setText(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")
        self.status_label.setText(f"已加载 {len(stats)} 个指标")
    
    def _update_table(self, stats: dict):
        """更新表格数据"""
        # 指标名称映射
        name_map = {
            "chat_api": "💬 Chat API",
            "embedding_api": "🔢 Embedding API",
            "vector_search": "🔍 向量检索",
            "keyword_search": "📝 关键词搜索",
            "knowledge_add": "➕ 知识库添加",
            "knowledge_update": "✏️ 知识库更新",
        }
        
        # 过滤有数据的指标
        active_stats = {k: v for k, v in stats.items() if v["count"] > 0}
        
        self.metrics_table.setRowCount(len(active_stats))
        
        for row, (name, s) in enumerate(active_stats.items()):
            display_name = name_map.get(name, name)
            
            self.metrics_table.setItem(row, 0, self._create_item(display_name))
            self.metrics_table.setItem(row, 1, self._create_item(str(s["count"])))
            self.metrics_table.setItem(row, 2, self._create_item(f"{s['success_rate']:.1%}"))
            self.metrics_table.setItem(row, 3, self._create_item(f"{s['avg_duration']*1000:.1f}ms"))
            self.metrics_table.setItem(row, 4, self._create_item(f"{s['min_duration']*1000:.1f}ms"))
            self.metrics_table.setItem(row, 5, self._create_item(f"{s['max_duration']*1000:.1f}ms"))
            self.metrics_table.setItem(row, 6, self._create_item(f"{s['p50_duration']*1000:.1f}ms"))
            self.metrics_table.setItem(row, 7, self._create_item(f"{s['p95_duration']*1000:.1f}ms"))
    
    def _create_item(self, text: str):
        """创建表格项"""
        from PySide6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item
    
    def _toggle_auto_refresh(self, checked: bool):
        """切换自动刷新"""
        self.auto_refresh = checked
        if checked:
            self.refresh_timer.start(5000)  # 5秒刷新一次
            self.status_label.setText("自动刷新已启用 (5秒)")
        else:
            self.refresh_timer.stop()
            self.status_label.setText("自动刷新已停止")
    
    def _export_report(self):
        """导出报告"""
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出性能报告", "performance_report.txt", 
            "文本文件 (*.txt);;Markdown (*.md);;所有文件 (*)"
        )
        
        if not save_path:
            return
        
        try:
            report = self.monitor.export_report()
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(report)
            
            InfoBar.success(
                title="导出成功",
                content=f"报告已保存到: {save_path}",
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
    
    def _clear_data(self):
        """清空数据"""
        from qfluentwidgets import MessageBox
        
        box = MessageBox(
            "清空性能数据",
            "确定要清空所有性能监控数据吗？\n此操作不可恢复。",
            self
        )
        
        if box.exec():
            self.monitor.clear_all()
            self._refresh_data()
            
            InfoBar.success(
                title="已清空",
                content="性能监控数据已清空",
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def refresh(self):
        """外部调用刷新"""
        self._refresh_data()
