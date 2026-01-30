# -*- coding: utf-8 -*-
"""
知识库管理界面 - 简化版（删除无用指标）

优化内容 (v2.3.0):
- 使用 ProgressThrottler 节流进度更新，避免UI卡顿
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QScrollArea, QTableWidgetItem, QHeaderView, 
    QAbstractItemView, QDialog, QFormLayout
)
from PySide6.QtCore import Qt, Signal, QThread, QObject

from qfluentwidgets import (
    CardWidget, BodyLabel, TitleLabel, SubtitleLabel,
    PushButton, PrimaryPushButton, TransparentPushButton,
    ComboBox, TableWidget, SearchLineEdit, SpinBox, 
    LineEdit, TextEdit, FluentIcon, ListWidget,
    MessageBox, InfoBar, InfoBarPosition
)

from core.shared_data import KnowledgeStore, KnowledgeItem
from core.ui_utils import ProgressThrottler
from core.validators import KnowledgeValidator
from core.search import AdvancedSearch, SearchMode


class RebuildIndexWorker(QObject):
    """重建索引工作线程"""
    finished = Signal(bool, str)
    failed = Signal(str)
    progress = Signal(str, int, int)

    def __init__(self):
        super().__init__()
        self._throttler = None

    def run(self):
        try:
            # 创建节流器，限制进度更新频率
            # min_interval=0.1: 最多每100ms更新一次
            # min_progress_change=0.02: 进度变化超过2%才更新
            self._throttler = ProgressThrottler(
                callback=lambda stage, current, total: self.progress.emit(str(stage), int(current), int(total)),
                min_interval=0.1,
                min_progress_change=0.02
            )

            def throttled_cb(stage: str, current: int, total: int):
                self._throttler.update(stage, current, total)

            success, message = KnowledgeStore().rebuild_vector_index(progress_callback=throttled_cb)
            
            # 确保最后一次进度更新被发送
            if self._throttler:
                self._throttler.finish()
            
            self.finished.emit(bool(success), str(message))
        except Exception as e:
            self.failed.emit(str(e))


class AddKnowledgeDialog(QDialog):
    """添加/编辑知识对话框"""
    
    def __init__(self, parent=None, knowledge_item=None):
        super().__init__(parent)
        self.knowledge_item = knowledge_item
        self.is_edit = knowledge_item is not None
        
        self.setWindowTitle("编辑知识" if self.is_edit else "添加知识")
        self.setFixedSize(550, 450)
        self.setModal(True)  # 设置为模态对话框
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)  # 置顶显示
        self.setStyleSheet("""
            QDialog {
                background-color: #FAFAFA;
            }
            QLabel {
                color: #333333;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # 标题
        title = TitleLabel("📚 编辑知识" if self.is_edit else "📚 添加新知识")
        layout.addWidget(title)
        
        # 问题
        q_card = CardWidget()
        q_layout = QVBoxLayout(q_card)
        q_layout.setContentsMargins(16, 12, 16, 12)
        q_layout.addWidget(BodyLabel("❓ 问题："))
        self.question_edit = LineEdit()
        self.question_edit.setPlaceholderText("输入用户可能问的问题...")
        q_layout.addWidget(self.question_edit)
        layout.addWidget(q_card)
        
        # 答案
        a_card = CardWidget()
        a_layout = QVBoxLayout(a_card)
        a_layout.setContentsMargins(16, 12, 16, 12)
        a_layout.addWidget(BodyLabel("💬 答案："))
        self.answer_edit = TextEdit()
        self.answer_edit.setPlaceholderText("输入标准答案...")
        self.answer_edit.setFixedHeight(100)
        a_layout.addWidget(self.answer_edit)
        layout.addWidget(a_card)
        
        # 关键词和分类
        meta_card = CardWidget()
        meta_layout = QFormLayout(meta_card)
        meta_layout.setContentsMargins(16, 12, 16, 12)
        
        self.keywords_edit = LineEdit()
        self.keywords_edit.setPlaceholderText("退货, 退款, 售后（逗号分隔）")
        meta_layout.addRow("🏷️ 关键词：", self.keywords_edit)
        
        self.category_combo = ComboBox()
        self.category_combo.addItems(["售后政策", "物流配送", "促销活动", "商品咨询", "支付问题", "服务咨询", "订单咨询", "商品信息", "通用"])
        meta_layout.addRow("📁 分类：", self.category_combo)
        
        layout.addWidget(meta_card)
        
        layout.addStretch()
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = PushButton("取消")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        self.save_btn = PrimaryPushButton(FluentIcon.SAVE, "保存")
        self.save_btn.setFixedWidth(100)
        self.save_btn.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.save_btn)
        
        layout.addLayout(btn_layout)
        
        # 如果是编辑模式，填充数据
        if self.is_edit:
            self._fill_data()
    
    def _fill_data(self):
        """填充编辑数据"""
        if not self.knowledge_item:
            return
        
        self.question_edit.setText(self.knowledge_item.question)
        self.answer_edit.setPlainText(self.knowledge_item.answer)
        self.keywords_edit.setText(", ".join(self.knowledge_item.keywords))
        
        # 设置分类
        index = self.category_combo.findText(self.knowledge_item.category)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        else:
            self.category_combo.setCurrentText(self.knowledge_item.category)
    
    def _validate_and_accept(self):
        """验证并保存"""
        # 收集数据
        data = {
            "question": self.question_edit.text(),
            "answer": self.answer_edit.toPlainText(),
            "keywords": self.keywords_edit.text(),
            "category": self.category_combo.currentText()
        }
        
        # 使用验证器验证
        valid, cleaned, errors = KnowledgeValidator.validate(data)
        
        if not valid:
            # 显示第一个错误
            InfoBar.warning(
                title="数据验证失败",
                content=errors[0] if errors else "请检查输入数据",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        self.accept()
    
    def get_data(self):
        """获取输入数据"""
        keywords = [k.strip() for k in self.keywords_edit.text().split(",") if k.strip()]
        return {
            "question": self.question_edit.text().strip(),
            "answer": self.answer_edit.toPlainText().strip(),
            "keywords": keywords,
            "category": self.category_combo.currentText()
        }


class KnowledgeTreePanel(QFrame):
    """知识库分类面板"""
    
    category_selected = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setStyleSheet("""
            QFrame { 
                border-right: 1px solid rgba(0,0,0,0.1);
                background-color: #FAFAFA;
            }
        """)
        
        self.knowledge_store = KnowledgeStore()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(16)
        
        # 标题
        title = TitleLabel("📚 知识分类")
        layout.addWidget(title)
        
        # 分类列表
        self.list_widget = ListWidget()
        self.list_widget.setStyleSheet("""
            ListWidget {
                border: none;
                background-color: transparent;
                outline: none;
            }
            ListWidget::item {
                padding: 8px 16px;
                border-radius: 8px;
                margin: 1px 0;
                border: none;
                outline: none;
            }
            ListWidget::item:hover {
                background-color: rgba(0, 120, 212, 0.1);
                border: none;
            }
            ListWidget::item:selected {
                background-color: rgba(0, 120, 212, 0.2);
                color: #0078d4;
                border: none;
                outline: none;
            }
            ListWidget::item:focus {
                border: none;
                outline: none;
            }
        """)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget, 1)
        
        self._load_data()
    
    def _load_data(self):
        self.list_widget.clear()
        
        # 全部
        total = len(self.knowledge_store.items)
        self.list_widget.addItem(f"📋 全部知识 ({total})")
        
        # 分类统计
        categories = {}
        for item in self.knowledge_store.items:
            cat = item.category
            categories[cat] = categories.get(cat, 0) + 1
        
        # 分类图标
        cat_icons = {
            "售后政策": "🔄",
            "物流配送": "🚚",
            "促销活动": "🎉",
            "商品咨询": "📦",
            "支付问题": "💳",
            "服务咨询": "💁",
            "订单咨询": "🧾",
            "通用": "📝"
        }
        
        for cat, count in sorted(categories.items()):
            icon = cat_icons.get(cat, "📁")
            self.list_widget.addItem(f"{icon} {cat} ({count})")
    
    def refresh(self):
        self._load_data()
    
    def _on_item_clicked(self, item):
        text = item.text()
        if "全部知识" in text:
            self.category_selected.emit("全部")
        else:
            parts = text.split(" ")
            if len(parts) >= 2:
                cat = " ".join(parts[1:-1])
                if cat.endswith(")"):
                    cat = cat.rsplit(" ", 1)[0]
                self.category_selected.emit(cat)


class DocumentListPanel(QFrame):
    """知识列表面板"""
    
    item_selected = Signal(object)
    item_deleted = Signal(str)
    item_added = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.knowledge_store = KnowledgeStore()
        self.current_items = []
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # 标题行
        top = QHBoxLayout()
        self.title = SubtitleLabel("📋 知识列表")
        top.addWidget(self.title)
        top.addStretch()
        
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索知识...")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(self._on_search)
        top.addWidget(self.search)
        
        # 搜索模式选择
        self.search_mode = ComboBox()
        self.search_mode.addItems(["包含", "精确", "模糊", "前缀"])
        self.search_mode.setFixedWidth(80)
        self.search_mode.currentTextChanged.connect(lambda: self._on_search(self.search.text()))
        top.addWidget(self.search_mode)
        
        self.add_btn = PrimaryPushButton(FluentIcon.ADD, "添加知识")
        self.add_btn.clicked.connect(self._add_knowledge)
        top.addWidget(self.add_btn)
        
        layout.addLayout(top)
        
        # 表格
        self.table = TableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "问题", "分类", "关键词", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 80)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellClicked.connect(self._on_row_clicked)
        
        layout.addWidget(self.table, 1)
        
        self._load_all()
    
    def _load_all(self):
        self.current_items = self.knowledge_store.get_all_items()
        self._refresh_table()
    
    def load_by_category(self, category: str):
        self.title.setText(f"📋 知识列表 - {category}")
        if category == "全部":
            self.current_items = self.knowledge_store.get_all_items()
        else:
            self.current_items = [i for i in self.knowledge_store.items if i.category == category]
        self._refresh_table()
    
    def _on_search(self, text: str):
        if not text:
            self._load_all()
        else:
            # 获取搜索模式
            mode_map = {
                "包含": SearchMode.CONTAINS,
                "精确": SearchMode.EXACT,
                "模糊": SearchMode.FUZZY,
                "前缀": SearchMode.PREFIX
            }
            mode = mode_map.get(self.search_mode.currentText(), SearchMode.CONTAINS)
            
            # 使用高级搜索
            searcher = AdvancedSearch(
                self.knowledge_store.items,
                search_fields=["question", "answer", "keywords"]
            )
            results = searcher.search(text, mode=mode)
            self.current_items = [r.item for r in results]
        self._refresh_table()
    
    def _refresh_table(self):
        self.table.setRowCount(len(self.current_items))
        
        for i, item in enumerate(self.current_items):
            self.table.setItem(i, 0, QTableWidgetItem(item.id))
            q_text = item.question[:35] + "..." if len(item.question) > 35 else item.question
            self.table.setItem(i, 1, QTableWidgetItem(q_text))
            self.table.setItem(i, 2, QTableWidgetItem(item.category))
            self.table.setItem(i, 3, QTableWidgetItem(", ".join(item.keywords[:3])))
            self.table.setItem(i, 4, QTableWidgetItem("🗑️ 删除"))
    
    def _on_row_clicked(self, row: int, column: int):
        if 0 <= row < len(self.current_items):
            if column == 4:
                self._delete_item(row)
            else:
                self.item_selected.emit(self.current_items[row])
    
    def _add_knowledge(self):
        """添加知识"""
        try:
            dialog = AddKnowledgeDialog(self.window())  # 使用顶层窗口作为父窗口
            result = dialog.exec()
            if result:
                data = dialog.get_data()
                if data["question"] and data["answer"]:
                    self.knowledge_store.add_item(
                        question=data["question"],
                        answer=data["answer"],
                        keywords=data["keywords"],
                        category=data["category"]
                    )
                    self._load_all()
                    self.item_added.emit()
                    index_error = getattr(self.knowledge_store, "last_vector_index_error", None)
                    if isinstance(index_error, dict) and index_error.get("type") == "dimension_mismatch":
                        InfoBar.success(
                            title="添加成功",
                            content="知识已添加到知识库（向量索引未更新）",
                            parent=self,
                            position=InfoBarPosition.TOP
                        )
                        InfoBar.warning(
                            title="需要重建索引",
                            content="检测到Embedding维度变化，请点击“重建向量索引”以恢复向量检索效果",
                            parent=self,
                            position=InfoBarPosition.TOP
                        )
                        return
                    InfoBar.success(
                        title="添加成功",
                        content="知识已添加到知识库",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
        except Exception as e:
            print(f"添加知识出错: {e}")
            InfoBar.error(
                title="添加失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def _delete_item(self, row: int):
        item = self.current_items[row]
        
        w = MessageBox("确认删除", f"确定要删除知识 {item.id} 吗？\n\n问题：{item.question[:30]}...", self)
        if w.exec():
            self.knowledge_store.delete_item(item.id)
            self._load_all()
            self.item_deleted.emit(item.id)
            InfoBar.success(
                title="删除成功",
                content=f"知识 {item.id} 已删除",
                parent=self,
                position=InfoBarPosition.TOP
            )


class DocumentDetailPanel(QFrame):
    """知识详情面板 - 集成RAG配置"""
    
    index_rebuilt = Signal()
    item_updated = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(350)
        self.setStyleSheet("QFrame { border-left: 1px solid rgba(0,0,0,0.1); }")
        
        from core.config import Config
        from core.shared_data import KnowledgeStore
        self.config = Config()
        self.knowledge_store = KnowledgeStore()
        self.current_item = None

        self._rebuild_running = False
        self._rebuild_thread: QThread | None = None
        self._rebuild_worker: RebuildIndexWorker | None = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        self.title = SubtitleLabel("📄 知识详情")
        layout.addWidget(self.title)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")
        
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(12)
        
        self._init_form()
        
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        
        # 编辑按钮
        self.edit_btn = PrimaryPushButton(FluentIcon.EDIT, "编辑知识")
        self.edit_btn.clicked.connect(self._edit_item)
        self.edit_btn.setEnabled(False)
        layout.addWidget(self.edit_btn)
        
        # 配置卡片
        config_card = CardWidget()
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(12, 12, 12, 12)
        config_layout.setSpacing(8)
        
        config_title = BodyLabel("⚙️ RAG配置")
        config_title.setStyleSheet("font-weight: bold;")
        config_layout.addWidget(config_title)
        
        size_row = QHBoxLayout()
        size_row.addWidget(BodyLabel("Chunk大小:"))
        self.chunk_size = SpinBox()
        self.chunk_size.setRange(100, 2000)
        self.chunk_size.setValue(self.config.get("chunk_size", 500))
        self.chunk_size.valueChanged.connect(self._save_config)
        size_row.addWidget(self.chunk_size)
        config_layout.addLayout(size_row)
        
        overlap_row = QHBoxLayout()
        overlap_row.addWidget(BodyLabel("重叠大小:"))
        self.overlap = SpinBox()
        self.overlap.setRange(0, 500)
        self.overlap.setValue(self.config.get("chunk_overlap", 50))
        self.overlap.valueChanged.connect(self._save_config)
        overlap_row.addWidget(self.overlap)
        config_layout.addLayout(overlap_row)
        
        model_row = QHBoxLayout()
        model_row.addWidget(BodyLabel("Embedding:"))
        self.model_combo = ComboBox()
        self.model_combo.addItems(["bge-large-zh", "m3e-base", "text-embedding-ada-002"])
        # 设置当前选中的模型
        current_model = self.config.get("embedding_model", "bge-large-zh")
        index = self.model_combo.findText(current_model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        model_row.addWidget(self.model_combo)
        config_layout.addLayout(model_row)
        
        # 重建索引按钮
        self.rebuild_btn = PrimaryPushButton(FluentIcon.SYNC, "重建向量索引")
        self.rebuild_btn.clicked.connect(self._rebuild_index)
        config_layout.addWidget(self.rebuild_btn)
        
        # 索引状态
        self.index_status = BodyLabel("📊 索引状态: 未知")
        self.index_status.setStyleSheet("color: gray; font-size: 11px;")
        config_layout.addWidget(self.index_status)
        
        layout.addWidget(config_card)
        
        # 更新索引状态
        self._update_index_status()
    
    def _edit_item(self):
        """编辑知识"""
        if not self.current_item:
            return
        
        try:
            dialog = AddKnowledgeDialog(self.window(), self.current_item)
            result = dialog.exec()
            if result:
                data = dialog.get_data()
                self.knowledge_store.update_item(
                    self.current_item.id,
                    question=data["question"],
                    answer=data["answer"],
                    keywords=data["keywords"],
                    category=data["category"]
                )
                # 重新加载知识
                updated = self.knowledge_store.get_item_by_id(self.current_item.id)
                if updated:
                    self.load_item(updated)
                self.item_updated.emit()
                index_error = getattr(self.knowledge_store, "last_vector_index_error", None)
                if isinstance(index_error, dict) and index_error.get("type") == "dimension_mismatch":
                    InfoBar.success(
                        title="更新成功",
                        content="知识已更新（向量索引未更新）",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
                    InfoBar.warning(
                        title="需要重建索引",
                        content="检测到Embedding维度变化，请点击“重建向量索引”以恢复向量检索效果",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
                    return
                InfoBar.success(
                    title="更新成功",
                    content="知识已更新，向量索引已同步",
                    parent=self,
                    position=InfoBarPosition.TOP
                )
        except Exception as e:
            print(f"编辑知识出错: {e}")
            InfoBar.error(
                title="更新失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def _save_config(self):
        """保存配置"""
        self.config.set("chunk_size", self.chunk_size.value())
        self.config.set("chunk_overlap", self.overlap.value())
        self.config.set("embedding_model", self.model_combo.currentText())
        InfoBar.success(
            title="配置已保存",
            content="RAG配置已更新",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=1500
        )

    def _on_model_changed(self, model: str):
        old_model = self.config.get("embedding_model", "bge-large-zh")
        if model == old_model:
            self._save_config()
            return

        from core.vector_store import VectorStore
        vs = VectorStore()
        index_model = getattr(vs, "embedding_model", None)

        warn_parts = []
        warn_parts.append(f"当前索引基于模型: {index_model or old_model}")
        warn_parts.append(f"新选择的模型: {model}")
        warn_parts.append("建议切换模型后立即重建向量索引，以避免召回异常。")

        msg = "\n".join(warn_parts)

        box = MessageBox("切换Embedding模型", msg, self)
        box.yesButton.setText("保存并重建索引")
        box.cancelButton.setText("仅保存")

        if box.exec():
            self._save_config()
            self._rebuild_index()
        else:
            self._save_config()
        self._update_index_status()
    
    def _rebuild_index(self):
        """重建向量索引"""
        if self._rebuild_running:
            return

        self._rebuild_running = True
        self.rebuild_btn.setEnabled(False)
        self.rebuild_btn.setText("重建中...")
        self.index_status.setText("📊 索引状态: 重建中...")

        self._rebuild_thread = QThread()
        self._rebuild_worker = RebuildIndexWorker()
        self._rebuild_worker.moveToThread(self._rebuild_thread)

        self._rebuild_thread.started.connect(self._rebuild_worker.run)
        self._rebuild_worker.finished.connect(self._on_rebuild_finished)
        self._rebuild_worker.failed.connect(self._on_rebuild_failed)
        self._rebuild_worker.progress.connect(self._on_rebuild_progress)
        self._rebuild_worker.finished.connect(self._rebuild_thread.quit)
        self._rebuild_worker.failed.connect(self._rebuild_thread.quit)
        self._rebuild_thread.finished.connect(self._cleanup_rebuild_thread)

        self._rebuild_thread.start()

    def _on_rebuild_progress(self, stage: str, current: int, total: int):
        if total <= 0:
            total = 1
        current = max(0, min(current, total))
        self.index_status.setText(f"📊 索引状态: {stage} {current}/{total}")

    def _on_rebuild_finished(self, success: bool, message: str):
        if success:
            InfoBar.success(
                title="重建成功",
                content=message,
                parent=self,
                position=InfoBarPosition.TOP
            )
            self.index_rebuilt.emit()
        else:
            InfoBar.error(
                title="重建失败",
                content=message,
                parent=self,
                position=InfoBarPosition.TOP
            )
        self._finish_rebuild_ui()

    def _on_rebuild_failed(self, message: str):
        InfoBar.error(
            title="重建失败",
            content=message,
            parent=self,
            position=InfoBarPosition.TOP
        )
        self._finish_rebuild_ui()

    def _finish_rebuild_ui(self):
        self._rebuild_running = False
        self.rebuild_btn.setEnabled(True)
        self.rebuild_btn.setText("重建向量索引")
        self._update_index_status()

    def _cleanup_rebuild_thread(self):
        if self._rebuild_worker is not None:
            self._rebuild_worker.deleteLater()
            self._rebuild_worker = None
        if self._rebuild_thread is not None:
            self._rebuild_thread.deleteLater()
            self._rebuild_thread = None
    
    def _update_index_status(self):
        """更新索引状态"""
        try:
            from core.vector_store import VectorStore
            vs = VectorStore()
            count = vs.count
            dim = getattr(vs, "dimension", None)
            built_model = getattr(vs, "embedding_model", None)
            current_model = self.config.get("embedding_model", "bge-large-zh")
            if count > 0 and built_model and built_model != current_model:
                self.index_status.setText(f"⚠️ 需要重建索引: {built_model} → {current_model}")
            else:
                if dim:
                    self.index_status.setText(f"📊 索引状态: {count} 条向量（维度 {dim}）")
                else:
                    self.index_status.setText(f"📊 索引状态: {count} 条向量")
        except:
            self.index_status.setText("📊 索引状态: 未初始化")
    
    def _init_form(self):
        info_card = CardWidget()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setSpacing(8)
        
        self.id_label = BodyLabel("🆔 ID：-")
        info_layout.addWidget(self.id_label)
        
        self.cat_label = BodyLabel("📁 分类：-")
        info_layout.addWidget(self.cat_label)
        
        self.keywords_label = BodyLabel("🏷️ 关键词：-")
        self.keywords_label.setWordWrap(True)
        info_layout.addWidget(self.keywords_label)
        
        self.content_layout.addWidget(info_card)
        
        q_card = CardWidget()
        q_layout = QVBoxLayout(q_card)
        q_layout.setContentsMargins(12, 12, 12, 12)
        
        q_title = BodyLabel("❓ 问题")
        q_title.setStyleSheet("font-weight: bold; color: #1890ff;")
        q_layout.addWidget(q_title)
        
        self.question_label = BodyLabel("-")
        self.question_label.setWordWrap(True)
        q_layout.addWidget(self.question_label)
        
        self.content_layout.addWidget(q_card)
        
        a_card = CardWidget()
        a_layout = QVBoxLayout(a_card)
        a_layout.setContentsMargins(12, 12, 12, 12)
        
        a_title = BodyLabel("💬 答案")
        a_title.setStyleSheet("font-weight: bold; color: #52c41a;")
        a_layout.addWidget(a_title)
        
        self.answer_label = BodyLabel("-")
        self.answer_label.setWordWrap(True)
        a_layout.addWidget(self.answer_label)
        
        self.content_layout.addWidget(a_card)
        self.content_layout.addStretch()
    
    def load_item(self, item):
        self.current_item = item
        self.edit_btn.setEnabled(True)
        
        self.title.setText(f"📄 知识详情 - {item.id}")
        self.id_label.setText(f"🆔 ID：{item.id}")
        self.cat_label.setText(f"📁 分类：{item.category}")
        self.keywords_label.setText(f"🏷️ 关键词：{', '.join(item.keywords)}")
        self.question_label.setText(item.question)
        self.answer_label.setText(item.answer)


class PublishToolbar(QFrame):
    """底部工具栏 - 显示知识库统计"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet("""
            PublishToolbar { 
                border: none;
                border-top: 1px solid rgba(0,0,0,0.1);
                background-color: #FAFAFA;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(16)
        
        # 知识库统计
        self.stats_label = BodyLabel(f"📚 知识库共 {len(KnowledgeStore().items)} 条知识")
        self.stats_label.setStyleSheet("color: gray;")
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
    
    def refresh_stats(self):
        """刷新统计"""
        self.stats_label.setText(f"📚 知识库共 {len(KnowledgeStore().items)} 条知识")


class KnowledgeInterface(QWidget):
    """知识库管理界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("knowledge_interface")
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        self.tree_panel = KnowledgeTreePanel()
        self.tree_panel.category_selected.connect(self._on_category_selected)
        content_layout.addWidget(self.tree_panel)
        
        self.doc_list_panel = DocumentListPanel()
        self.doc_list_panel.item_selected.connect(self._on_item_selected)
        self.doc_list_panel.item_deleted.connect(self._on_item_changed)
        self.doc_list_panel.item_added.connect(self._on_item_changed)
        content_layout.addWidget(self.doc_list_panel, 1)
        
        self.detail_panel = DocumentDetailPanel()
        self.detail_panel.item_updated.connect(self._on_item_changed)
        content_layout.addWidget(self.detail_panel)
        
        layout.addWidget(content, 1)
        
        self.toolbar = PublishToolbar()
        layout.addWidget(self.toolbar)
    
    def _on_category_selected(self, category: str):
        self.doc_list_panel.load_by_category(category)
    
    def _on_item_selected(self, item: KnowledgeItem):
        self.detail_panel.load_item(item)
    
    def _on_item_changed(self, *args):
        """知识变更后刷新"""
        self.tree_panel.refresh()
        self.toolbar.refresh_stats()
