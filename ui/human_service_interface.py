# -*- coding: utf-8 -*-
"""
人工客服界面 - 处理转入的人工对话
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QScrollArea, QSizePolicy, QSplitter
)
from PySide6.QtCore import Qt, Signal, QTimer

from qfluentwidgets import (
    PushButton, PrimaryPushButton, LineEdit,
    CardWidget, BodyLabel, TitleLabel, SubtitleLabel,
    FluentIcon, InfoBar, InfoBarPosition, ComboBox
)

from core.conversation import ConversationManager, Conversation


class PendingQueueItem(CardWidget):
    """待处理队列项"""
    
    clicked = Signal(str)
    
    def __init__(self, conversation: Conversation, parent=None):
        super().__init__(parent)
        self.conv_id = conversation.id
        self.conv = conversation
        
        self.setFixedHeight(70)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        
        # 标题行
        title_row = QHBoxLayout()
        
        # 状态图标
        status_icon = "🔴" if conversation.status == Conversation.STATUS_PENDING_HUMAN else "🟢"
        icon_label = BodyLabel(status_icon)
        title_row.addWidget(icon_label)
        
        # 对话标题
        title = conversation.title[:25] + "..." if len(conversation.title) > 25 else conversation.title
        self.title_label = BodyLabel(title)
        self.title_label.setStyleSheet("font-weight: bold;")
        title_row.addWidget(self.title_label, 1)
        
        layout.addLayout(title_row)
        
        # 最后一条消息预览
        if conversation.messages:
            last_msg = conversation.messages[-1]
            preview = last_msg.content[:40] + "..." if len(last_msg.content) > 40 else last_msg.content
            self.preview_label = BodyLabel(preview)
            self.preview_label.setStyleSheet("color: gray; font-size: 12px;")
            layout.addWidget(self.preview_label)
        
        # 等待时间
        self.time_label = BodyLabel(f"转入时间: {conversation.updated_at}")
        self.time_label.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(self.time_label)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.conv_id)


class PendingQueuePanel(QFrame):
    """待处理队列面板"""
    
    conversation_selected = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conv_manager = ConversationManager()
        self.queue_items = {}
        
        self.setFixedWidth(280)
        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border-right: 1px solid rgba(0,0,0,0.1);
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(12)
        
        # 标题
        title = TitleLabel("📋 待处理队列")
        layout.addWidget(title)
        
        # 统计信息
        self.stats_label = BodyLabel("待处理: 0 | 处理中: 0")
        self.stats_label.setStyleSheet("color: gray;")
        layout.addWidget(self.stats_label)
        
        # 刷新按钮
        self.refresh_btn = PushButton(FluentIcon.SYNC, "刷新队列")
        self.refresh_btn.clicked.connect(self.refresh_queue)
        layout.addWidget(self.refresh_btn)
        
        # 队列列表
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()
        
        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll, 1)
        
        # 定时刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_queue)
        self.refresh_timer.start(5000)  # 每5秒刷新
        
        self.refresh_queue()
    
    def refresh_queue(self):
        """刷新待处理队列"""
        # 清空现有项
        for item in self.queue_items.values():
            item.deleteLater()
        self.queue_items.clear()
        
        while self.list_layout.count() > 0:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 重新加载对话
        self.conv_manager._load_conversations()
        
        # 获取需要人工处理的对话
        pending_count = 0
        handling_count = 0
        
        for conv in self.conv_manager.get_all_conversations():
            if conv.status in [Conversation.STATUS_PENDING_HUMAN, Conversation.STATUS_HUMAN_HANDLING]:
                item = PendingQueueItem(conv)
                item.clicked.connect(self._on_item_clicked)
                self.list_layout.addWidget(item)
                self.queue_items[conv.id] = item
                
                if conv.status == Conversation.STATUS_PENDING_HUMAN:
                    pending_count += 1
                else:
                    handling_count += 1
        
        self.list_layout.addStretch()
        self.stats_label.setText(f"待处理: {pending_count} | 处理中: {handling_count}")
    
    def _on_item_clicked(self, conv_id: str):
        self.conversation_selected.emit(conv_id)


class HumanChatPanel(QFrame):
    """人工客服对话面板"""
    
    message_sent = Signal(str, str)  # conv_id, message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conv_manager = ConversationManager()
        self.current_conv = None
        self._rendered_message_count = 0
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 顶部信息栏
        self.header = CardWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        
        self.conv_title = SubtitleLabel("请选择一个对话")
        header_layout.addWidget(self.conv_title)
        header_layout.addStretch()
        
        self.status_label = BodyLabel("")
        self.status_label.setStyleSheet("color: #1890ff;")
        header_layout.addWidget(self.status_label)
        
        self.accept_btn = PrimaryPushButton(FluentIcon.ACCEPT, "接入对话")
        self.accept_btn.clicked.connect(self._accept_conversation)
        self.accept_btn.setVisible(False)
        header_layout.addWidget(self.accept_btn)
        
        self.close_btn = PushButton(FluentIcon.CLOSE, "结束服务")
        self.close_btn.clicked.connect(self._close_conversation)
        self.close_btn.setVisible(False)
        header_layout.addWidget(self.close_btn)
        
        layout.addWidget(self.header)
        
        # 消息区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")
        
        self.msg_container = QWidget()
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(24, 16, 24, 16)
        self.msg_layout.setSpacing(12)
        self.msg_layout.addStretch()
        
        self.scroll.setWidget(self.msg_container)
        layout.addWidget(self.scroll, 1)
        
        # 输入区域
        self.input_card = CardWidget()
        input_layout = QHBoxLayout(self.input_card)
        input_layout.setContentsMargins(16, 8, 16, 8)
        input_layout.setSpacing(12)
        
        self.input_edit = LineEdit()
        self.input_edit.setPlaceholderText("输入回复内容...")
        self.input_edit.setFixedHeight(44)
        self.input_edit.returnPressed.connect(self._send_message)
        self.input_edit.setEnabled(False)
        input_layout.addWidget(self.input_edit, 1)
        
        self.send_btn = PrimaryPushButton(FluentIcon.SEND, "发送")
        self.send_btn.setFixedSize(80, 38)
        self.send_btn.clicked.connect(self._send_message)
        self.send_btn.setEnabled(False)
        input_layout.addWidget(self.send_btn)
        
        input_container = QWidget()
        ic_layout = QHBoxLayout(input_container)
        ic_layout.setContentsMargins(24, 12, 24, 16)
        ic_layout.addWidget(self.input_card)
        layout.addWidget(input_container)
        
        # 消息刷新定时器
        self.msg_timer = QTimer()
        self.msg_timer.timeout.connect(self._refresh_messages)
        self.msg_timer.start(2000)  # 每2秒刷新消息
    
    def load_conversation(self, conv_id: str):
        """加载对话"""
        self.conv_manager._load_conversations()
        conv = self.conv_manager.get_conversation(conv_id)
        if not conv:
            return
        
        self.current_conv = conv
        self.conv_title.setText(f"📞 {conv.title}")
        
        # 根据状态显示不同按钮
        if conv.status == Conversation.STATUS_PENDING_HUMAN:
            self.status_label.setText("⏳ 等待接入")
            self.accept_btn.setVisible(True)
            self.close_btn.setVisible(False)
            self.input_edit.setEnabled(False)
            self.send_btn.setEnabled(False)
        elif conv.status == Conversation.STATUS_HUMAN_HANDLING:
            self.status_label.setText("🟢 服务中")
            self.accept_btn.setVisible(False)
            self.close_btn.setVisible(True)
            self.input_edit.setEnabled(True)
            self.send_btn.setEnabled(True)
        else:
            self.status_label.setText("")
            self.accept_btn.setVisible(False)
            self.close_btn.setVisible(False)
            self.input_edit.setEnabled(False)
            self.send_btn.setEnabled(False)
        
        self._display_messages()
        self._rendered_message_count = len(self.current_conv.messages) if self.current_conv else 0
    
    def _display_messages(self):
        """显示消息"""
        # 清空现有消息
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.current_conv:
            return
        
        stretch = self.msg_layout.takeAt(self.msg_layout.count() - 1)
        
        for msg in self.current_conv.messages:
            bubble = self._create_bubble(msg.role, msg.content)
            
            row = QHBoxLayout()
            if msg.role == "user":
                # 客户消息在左边
                row.addWidget(bubble)
                row.addStretch()
            else:
                # 客服/AI消息在右边
                row.addStretch()
                row.addWidget(bubble)
            
            container = QWidget()
            container.setLayout(row)
            self.msg_layout.addWidget(container)
        
        self.msg_layout.addStretch()
        
        # 滚动到底部
        QTimer.singleShot(50, self._scroll_bottom)
        self._rendered_message_count = len(self.current_conv.messages) if self.current_conv else 0
    
    def _create_bubble(self, role: str, content: str):
        """创建消息气泡"""
        bubble = QFrame()
        bubble.setMaximumWidth(500)
        layout = QVBoxLayout(bubble)
        layout.setContentsMargins(12, 8, 12, 8)
        
        if role == "user":
            # 客户消息 - 浅蓝色
            bubble.setStyleSheet("""
                QFrame {
                    background-color: #bbdefb;
                    border-radius: 12px;
                }
            """)
            label = BodyLabel(content)
            label.setWordWrap(True)
        else:
            # 客服/AI消息 - 白色背景
            bubble.setStyleSheet("""
                QFrame {
                    background-color: #ffffff;
                    border-radius: 12px;
                }
            """)
            header = BodyLabel("👨‍💼 人工客服" if "[人工客服]" in content else "🤖 AI助手")
            header.setStyleSheet("font-weight: bold; color: #1890ff;")
            layout.addWidget(header)
            label = BodyLabel(content)
            label.setWordWrap(True)
        
        layout.addWidget(label)
        return bubble
    
    def _scroll_bottom(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    def _accept_conversation(self):
        """接入对话"""
        if self.current_conv:
            self.current_conv.accept_by_human()
            self.conv_manager._save_conversation(self.current_conv)
            self.load_conversation(self.current_conv.id)
            
            InfoBar.success(
                title="接入成功",
                content="您已接入该对话，可以开始回复",
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def _close_conversation(self):
        """结束服务"""
        if self.current_conv:
            self.current_conv.close_human_service()
            self.conv_manager._save_conversation(self.current_conv)
            self.load_conversation(self.current_conv.id)
            
            InfoBar.success(
                title="服务已结束",
                content="人工服务已关闭",
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def _send_message(self):
        """发送消息"""
        if not self.current_conv or self.current_conv.status != Conversation.STATUS_HUMAN_HANDLING:
            return
        
        text = self.input_edit.text().strip()
        if not text:
            return
        
        # 添加人工客服消息（使用 assistant 角色以便显示在用户对话页面）
        self.current_conv.add_message("assistant", f"[人工客服] {text}")
        self.conv_manager._save_conversation(self.current_conv)
        
        self.input_edit.clear()
        self._display_messages()
        self._rendered_message_count = len(self.current_conv.messages) if self.current_conv else 0
        
        self.message_sent.emit(self.current_conv.id, text)
    
    def _refresh_messages(self):
        """刷新消息"""
        if self.current_conv:
            self.conv_manager._load_conversations()
            new_conv = self.conv_manager.get_conversation(self.current_conv.id)
            if not new_conv:
                return
            self.current_conv = new_conv
            if len(self.current_conv.messages) != self._rendered_message_count:
                self._display_messages()


class HumanServiceInterface(QWidget):
    """人工客服界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("human_service_interface")
        self._init_ui()
        self._connect_signals()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 待处理队列
        self.queue_panel = PendingQueuePanel()
        layout.addWidget(self.queue_panel)
        
        # 对话处理面板
        self.chat_panel = HumanChatPanel()
        layout.addWidget(self.chat_panel, 1)
    
    def _connect_signals(self):
        self.queue_panel.conversation_selected.connect(self.chat_panel.load_conversation)
        self.chat_panel.message_sent.connect(self._on_message_sent)
    
    def _on_message_sent(self, conv_id: str, message: str):
        """消息发送后刷新队列"""
        self.queue_panel.refresh_queue()
