# -*- coding: utf-8 -*-
"""
数据统计界面
提供系统使用情况统计和可视化展示
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QGridLayout, QFileDialog, QHeaderView, QScrollArea
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from qfluentwidgets import (
    CardWidget, BodyLabel, TitleLabel, SubtitleLabel,
    PushButton, PrimaryPushButton, TableWidget, 
    FluentIcon, InfoBar, InfoBarPosition, ProgressBar
)

from core.statistics import StatisticsManager


class StatCard(CardWidget):
    """统计卡片"""
    
    def __init__(self, title: str, icon: str = "📊", parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        
        # 标题行
        title_row = QHBoxLayout()
        self.icon_label = BodyLabel(icon)
        self.icon_label.setStyleSheet("font-size: 18px;")
        title_row.addWidget(self.icon_label)
        
        self.title_label = BodyLabel(title)
        self.title_label.setStyleSheet("color: gray; font-size: 12px;")
        title_row.addWidget(self.title_label)
        title_row.addStretch()
        layout.addLayout(title_row)
        
        # 数值
        self.value_label = TitleLabel("--")
        self.value_label.setStyleSheet("font-size: 28px; font-weight: bold;")
        layout.addWidget(self.value_label)
        
        layout.addStretch()
    
    def set_value(self, value: str):
        self.value_label.setText(value)


class CategoryCard(CardWidget):
    """分类统计卡片"""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        self.title_label = SubtitleLabel(title)
        layout.addWidget(self.title_label)
        
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(6)
        layout.addLayout(self.content_layout)
        
        layout.addStretch()
    
    def set_data(self, data: dict):
        """设置分类数据"""
        # 清空现有内容
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not data:
            label = BodyLabel("暂无数据")
            label.setStyleSheet("color: gray;")
            self.content_layout.addWidget(label)
            return
        
        # 计算总数
        total = sum(data.values())
        
        # 按数量排序
        sorted_items = sorted(data.items(), key=lambda x: -x[1])[:5]  # 只显示前5个
        
        for cat, count in sorted_items:
            row = QHBoxLayout()
            
            name_label = BodyLabel(cat)
            name_label.setFixedWidth(100)
            row.addWidget(name_label)
            
            # 进度条
            progress = ProgressBar()
            progress.setRange(0, 100)
            progress.setValue(int(count / total * 100) if total > 0 else 0)
            progress.setFixedHeight(8)
            row.addWidget(progress, 1)
            
            count_label = BodyLabel(str(count))
            count_label.setFixedWidth(40)
            count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(count_label)
            
            self.content_layout.addLayout(row)


class StatisticsInterface(QWidget):
    """数据统计界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statistics_interface")
        
        self.stats_manager = StatisticsManager()
        
        self._init_ui()
        self._refresh_data()
    
    def _init_ui(self):
        # 使用滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # 标题栏
        header = QHBoxLayout()
        title = TitleLabel("📈 数据统计")
        header.addWidget(title)
        header.addStretch()
        
        # 刷新按钮
        self.refresh_btn = PushButton(FluentIcon.SYNC, "刷新")
        self.refresh_btn.clicked.connect(self._refresh_data)
        header.addWidget(self.refresh_btn)
        
        # 导出按钮
        self.export_btn = PushButton(FluentIcon.DOWNLOAD, "导出报告")
        self.export_btn.clicked.connect(self._export_report)
        header.addWidget(self.export_btn)
        
        layout.addLayout(header)
        
        # 概览卡片 - 第一行
        overview_row1 = QHBoxLayout()
        overview_row1.setSpacing(12)
        
        self.conv_card = StatCard("总对话数", "💬")
        overview_row1.addWidget(self.conv_card)
        
        self.msg_card = StatCard("总消息数", "📝")
        overview_row1.addWidget(self.msg_card)
        
        self.knowledge_card = StatCard("知识库条目", "📚")
        overview_row1.addWidget(self.knowledge_card)
        
        self.product_card = StatCard("商品数量", "🛒")
        overview_row1.addWidget(self.product_card)
        
        self.user_card = StatCard("用户数量", "👥")
        overview_row1.addWidget(self.user_card)
        
        layout.addLayout(overview_row1)
        
        # 时间范围统计 - 第二行
        time_row = QHBoxLayout()
        time_row.setSpacing(12)
        
        self.today_card = StatCard("今日对话", "📅")
        time_row.addWidget(self.today_card)
        
        self.week_card = StatCard("本周对话", "📆")
        time_row.addWidget(self.week_card)
        
        self.month_card = StatCard("本月对话", "🗓️")
        time_row.addWidget(self.month_card)
        
        layout.addLayout(time_row)
        
        # 分类统计和热门问题
        detail_row = QHBoxLayout()
        detail_row.setSpacing(12)
        
        # 知识库分类
        self.knowledge_cat_card = CategoryCard("📁 知识库分类分布")
        detail_row.addWidget(self.knowledge_cat_card)
        
        # 商品分类
        self.product_cat_card = CategoryCard("🏷️ 商品分类分布")
        detail_row.addWidget(self.product_cat_card)
        
        layout.addLayout(detail_row)
        
        # 热门问题
        hot_card = CardWidget()
        hot_layout = QVBoxLayout(hot_card)
        hot_layout.setContentsMargins(16, 16, 16, 16)
        
        hot_layout.addWidget(SubtitleLabel("🔥 热门问题 Top 10"))
        
        self.hot_table = TableWidget()
        self.hot_table.setColumnCount(3)
        self.hot_table.setHorizontalHeaderLabels(["排名", "问题", "次数"])
        self.hot_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.hot_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.hot_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.hot_table.setColumnWidth(0, 60)
        self.hot_table.setColumnWidth(2, 80)
        self.hot_table.setEditTriggers(TableWidget.NoEditTriggers)
        self.hot_table.setMinimumHeight(350)
        self.hot_table.verticalHeader().setDefaultSectionSize(32)  # 设置行高
        hot_layout.addWidget(self.hot_table)
        
        layout.addWidget(hot_card)
        
        # 每日趋势
        trend_card = CardWidget()
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(16, 16, 16, 16)
        
        trend_layout.addWidget(SubtitleLabel("📊 最近7天趋势"))
        
        self.trend_table = TableWidget()
        self.trend_table.setColumnCount(3)
        self.trend_table.setHorizontalHeaderLabels(["日期", "对话数", "消息数"])
        self.trend_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.trend_table.setEditTriggers(TableWidget.NoEditTriggers)
        self.trend_table.setMinimumHeight(280)
        self.trend_table.verticalHeader().setDefaultSectionSize(36)  # 设置行高
        trend_layout.addWidget(self.trend_table)
        
        layout.addWidget(trend_card)
        
        layout.addStretch()
        
        scroll.setWidget(content)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
    
    def _refresh_data(self):
        """刷新数据"""
        stats = self.stats_manager.get_usage_stats()
        
        # 更新概览卡片
        self.conv_card.set_value(str(stats.total_conversations))
        self.msg_card.set_value(str(stats.total_messages))
        self.knowledge_card.set_value(str(stats.total_knowledge_items))
        self.product_card.set_value(str(stats.total_products))
        self.user_card.set_value(str(stats.total_users))
        
        # 更新时间范围统计
        self.today_card.set_value(str(stats.conversations_today))
        self.week_card.set_value(str(stats.conversations_this_week))
        self.month_card.set_value(str(stats.conversations_this_month))
        
        # 更新分类统计
        self.knowledge_cat_card.set_data(stats.knowledge_by_category)
        self.product_cat_card.set_data(stats.products_by_category)
        
        # 更新热门问题
        self._update_hot_questions(stats.top_questions)
        
        # 更新每日趋势
        daily_stats = self.stats_manager.get_daily_stats(7)
        self._update_trend_table(daily_stats)
        
        InfoBar.success(
            title="刷新成功",
            content="统计数据已更新",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=1500
        )
    
    def _update_hot_questions(self, questions: list):
        """更新热门问题表格"""
        self.hot_table.setRowCount(len(questions))
        
        for row, (question, count) in enumerate(questions):
            from PySide6.QtWidgets import QTableWidgetItem
            
            rank_item = QTableWidgetItem(str(row + 1))
            rank_item.setTextAlignment(Qt.AlignCenter)
            self.hot_table.setItem(row, 0, rank_item)
            
            q_item = QTableWidgetItem(question)
            self.hot_table.setItem(row, 1, q_item)
            
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.hot_table.setItem(row, 2, count_item)
    
    def _update_trend_table(self, daily_stats: list):
        """更新趋势表格"""
        self.trend_table.setRowCount(len(daily_stats))
        
        for row, day in enumerate(daily_stats):
            from PySide6.QtWidgets import QTableWidgetItem
            
            date_item = QTableWidgetItem(day["date"])
            date_item.setTextAlignment(Qt.AlignCenter)
            self.trend_table.setItem(row, 0, date_item)
            
            conv_item = QTableWidgetItem(str(day["conversations"]))
            conv_item.setTextAlignment(Qt.AlignCenter)
            self.trend_table.setItem(row, 1, conv_item)
            
            msg_item = QTableWidgetItem(str(day["messages"]))
            msg_item.setTextAlignment(Qt.AlignCenter)
            self.trend_table.setItem(row, 2, msg_item)
    
    def _export_report(self):
        """导出报告"""
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出统计报告", "statistics_report.md",
            "Markdown (*.md);;文本文件 (*.txt);;所有文件 (*)"
        )
        
        if not save_path:
            return
        
        try:
            report = self.stats_manager.export_report()
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
    
    def refresh(self):
        """外部调用刷新"""
        self._refresh_data()
