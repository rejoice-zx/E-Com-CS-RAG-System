# -*- coding: utf-8 -*-
"""
商品管理界面 - 管理商品信息并自动同步到知识库
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QScrollArea, QTableWidgetItem, QHeaderView, 
    QAbstractItemView, QDialog, QFormLayout, QGridLayout, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize

from qfluentwidgets import (
    CardWidget, BodyLabel, TitleLabel, SubtitleLabel,
    PushButton, PrimaryPushButton, TransparentPushButton, TransparentToolButton,
    ComboBox, TableWidget, SearchLineEdit, SpinBox, 
    LineEdit, TextEdit, FluentIcon, ListWidget,
    MessageBox, InfoBar, InfoBarPosition, DoubleSpinBox
)

from core.shared_data import ProductStore, ProductItem
from core.validators import ProductValidator
from core.search import AdvancedSearch, SearchMode


class AddProductDialog(QDialog):
    """添加商品对话框"""

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
    
    def __init__(self, parent=None, product: ProductItem = None):
        super().__init__(parent)
        self.product = product
        self.is_edit = product is not None
        
        self.setWindowTitle("编辑商品" if self.is_edit else "添加商品")
        self.setFixedSize(600, 650)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
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
        layout.setSpacing(12)
        
        # 标题
        title = TitleLabel("🛍️ 编辑商品" if self.is_edit else "🛍️ 添加新商品")
        layout.addWidget(title)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(12)
        
        # 基本信息卡片
        basic_card = CardWidget()
        basic_layout = QFormLayout(basic_card)
        basic_layout.setContentsMargins(16, 16, 16, 16)
        basic_layout.setSpacing(12)
        
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("输入商品名称，如：华为Mate 60 Pro")
        basic_layout.addRow("📦 商品名称：", self.name_edit)
        
        self.price_spin = DoubleSpinBox()
        self.price_spin.setRange(0, 9999999)
        self.price_spin.setDecimals(2)
        self.price_spin.setValue(0)
        self.price_spin.setPrefix("¥ ")
        basic_layout.addRow("💰 价格：", self.price_spin)
        
        self.stock_spin = SpinBox()
        self.stock_spin.setRange(0, 999999)
        self.stock_spin.setValue(0)
        basic_layout.addRow("📊 库存数量：", self.stock_spin)
        
        self.category_combo = ComboBox()
        self.category_combo.addItems([
            "手机", "折叠屏手机", "平板电脑", "笔记本电脑", "耳机", 
            "智能音箱", "电视", "无人机", "运动相机", "游戏机", "其他"
        ])
        basic_layout.addRow("📁 商品分类：", self.category_combo)
        
        self.keywords_edit = LineEdit()
        self.keywords_edit.setPlaceholderText("关键词用逗号分隔，如：华为, 手机, 旗舰")
        basic_layout.addRow("🏷️ 关键词：", self.keywords_edit)
        
        content_layout.addWidget(basic_card)
        
        # 商品描述卡片
        desc_card = CardWidget()
        desc_layout = QVBoxLayout(desc_card)
        desc_layout.setContentsMargins(16, 12, 16, 12)
        desc_layout.addWidget(BodyLabel("📝 商品描述："))
        self.desc_edit = TextEdit()
        self.desc_edit.setPlaceholderText("详细描述商品特点、功能、材质等信息...")
        self.desc_edit.setFixedHeight(100)
        desc_layout.addWidget(self.desc_edit)
        content_layout.addWidget(desc_card)
        
        # 规格参数卡片
        spec_card = CardWidget()
        spec_layout = QVBoxLayout(spec_card)
        spec_layout.setContentsMargins(16, 12, 16, 12)
        
        spec_header = QHBoxLayout()
        spec_header.addWidget(BodyLabel("📋 规格参数："))
        spec_header.addStretch()
        add_spec_btn = TransparentPushButton(FluentIcon.ADD, "添加规格")
        add_spec_btn.setFixedHeight(32)
        add_spec_btn.setIconSize(QSize(14, 14))
        self._ensure_valid_font_point_size(add_spec_btn)
        add_spec_btn.clicked.connect(self._add_spec_row)
        spec_header.addWidget(add_spec_btn)
        spec_layout.addLayout(spec_header)
        
        # 规格参数表格
        self.spec_widget = QWidget()
        self.spec_layout = QVBoxLayout(self.spec_widget)
        self.spec_layout.setContentsMargins(0, 0, 0, 0)
        self.spec_layout.setSpacing(8)
        spec_layout.addWidget(self.spec_widget)
        
        content_layout.addWidget(spec_card)
        content_layout.addStretch()
        
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        
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
        
        # 初始化规格行列表
        self.spec_rows = []
        
        # 如果是编辑模式，填充数据
        if self.is_edit:
            self._fill_data()
        else:
            # 添加默认的两行规格
            self._add_spec_row()
            self._add_spec_row()
    
    def _add_spec_row(self):
        """添加规格行"""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        
        key_edit = LineEdit()
        key_edit.setPlaceholderText("规格名称，如：颜色")
        key_edit.setFixedWidth(150)
        row_layout.addWidget(key_edit)
        
        value_edit = LineEdit()
        value_edit.setPlaceholderText("规格值，如：雅川青")
        row_layout.addWidget(value_edit)
        
        del_btn = TransparentToolButton(FluentIcon.DELETE)
        del_btn.setFixedSize(36, 32)
        del_btn.setIconSize(QSize(14, 14))
        self._ensure_valid_font_point_size(del_btn)
        del_btn.clicked.connect(lambda: self._remove_spec_row(row_widget))
        row_layout.addWidget(del_btn)
        
        self.spec_layout.addWidget(row_widget)
        self.spec_rows.append((row_widget, key_edit, value_edit))
    
    def _remove_spec_row(self, row_widget):
        """删除规格行"""
        for i, (widget, _, _) in enumerate(self.spec_rows):
            if widget == row_widget:
                self.spec_layout.removeWidget(row_widget)
                row_widget.deleteLater()
                del self.spec_rows[i]
                break
    
    def _fill_data(self):
        """填充编辑数据"""
        if not self.product:
            return
        
        self.name_edit.setText(self.product.name)
        self.price_spin.setValue(self.product.price)
        self.stock_spin.setValue(self.product.stock)
        
        # 设置分类
        index = self.category_combo.findText(self.product.category)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        else:
            self.category_combo.setCurrentText(self.product.category)
        
        self.keywords_edit.setText(", ".join(self.product.keywords))
        self.desc_edit.setPlainText(self.product.description)
        
        # 填充规格
        for key, value in self.product.specifications.items():
            self._add_spec_row()
            _, key_edit, value_edit = self.spec_rows[-1]
            key_edit.setText(key)
            value_edit.setText(value)
    
    def _validate_and_accept(self):
        """验证并保存"""
        # 收集数据
        data = {
            "name": self.name_edit.text(),
            "price": self.price_spin.value(),
            "stock": self.stock_spin.value(),
            "category": self.category_combo.currentText(),
            "keywords": self.keywords_edit.text(),
            "description": self.desc_edit.toPlainText()
        }
        
        # 使用验证器验证
        valid, cleaned, errors = ProductValidator.validate(data)
        
        if not valid:
            # 显示第一个错误
            InfoBar.warning(
                title="数据验证失败",
                content=errors[0] if errors else "请检查输入数据",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        # 额外检查价格必须大于0
        if cleaned.get("price", 0) <= 0:
            InfoBar.warning(
                title="请设置价格",
                content="商品价格必须大于0",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        self.accept()
    
    def get_data(self):
        """获取输入数据"""
        keywords = [k.strip() for k in self.keywords_edit.text().split(",") if k.strip()]
        
        specs = {}
        for _, key_edit, value_edit in self.spec_rows:
            key = key_edit.text().strip()
            value = value_edit.text().strip()
            if key and value:
                specs[key] = value
        
        return {
            "name": self.name_edit.text().strip(),
            "price": self.price_spin.value(),
            "stock": self.stock_spin.value(),
            "category": self.category_combo.currentText(),
            "keywords": keywords,
            "description": self.desc_edit.toPlainText().strip(),
            "specifications": specs
        }


class ProductCategoryPanel(QFrame):
    """商品分类面板"""
    
    category_selected = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet("""
            QFrame { 
                border-right: 1px solid rgba(0,0,0,0.1);
                background-color: #FAFAFA;
            }
        """)
        
        self.product_store = ProductStore()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(16)
        
        # 标题
        title = TitleLabel("🛍️ 商品分类")
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
        """)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget, 1)
        
        self._load_data()
    
    def _load_data(self):
        self.list_widget.clear()
        
        # 全部
        total = len(self.product_store.products)
        self.list_widget.addItem(f"📋 全部商品 ({total})")
        
        # 分类统计
        categories = {}
        for product in self.product_store.products:
            cat = product.category
            categories[cat] = categories.get(cat, 0) + 1
        
        # 分类图标
        cat_icons = {
            "手机": "📱", "折叠屏手机": "📲", "平板电脑": "💻", "笔记本电脑": "💻",
            "耳机": "🎧", "智能音箱": "🔊", "电视": "📺", "无人机": "✈️",
            "运动相机": "📷", "游戏机": "🎮", "其他": "📦"
        }
        
        for cat, count in sorted(categories.items()):
            icon = cat_icons.get(cat, "📁")
            self.list_widget.addItem(f"{icon} {cat} ({count})")
    
    def refresh(self):
        self._load_data()
    
    def _on_item_clicked(self, item):
        text = item.text()
        if "全部商品" in text:
            self.category_selected.emit("全部")
        else:
            parts = text.split(" ")
            if len(parts) >= 2:
                cat = " ".join(parts[1:-1])
                if cat.endswith(")"):
                    cat = cat.rsplit(" ", 1)[0]
                self.category_selected.emit(cat)


class ProductListPanel(QFrame):
    """商品列表面板"""
    
    product_selected = Signal(object)
    product_deleted = Signal(str)
    product_added = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.product_store = ProductStore()
        self.current_products = []
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # 标题行
        top = QHBoxLayout()
        self.title = SubtitleLabel("📋 商品列表")
        top.addWidget(self.title)
        top.addStretch()
        
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索商品...")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(self._on_search)
        top.addWidget(self.search)
        
        # 搜索模式选择
        self.search_mode = ComboBox()
        self.search_mode.addItems(["包含", "精确", "模糊", "前缀"])
        self.search_mode.setFixedWidth(80)
        self.search_mode.currentTextChanged.connect(lambda: self._on_search(self.search.text()))
        top.addWidget(self.search_mode)
        
        self.add_btn = PrimaryPushButton(FluentIcon.ADD, "添加商品")
        self.add_btn.clicked.connect(self._add_product)
        top.addWidget(self.add_btn)
        
        layout.addLayout(top)
        
        # 表格
        self.table = TableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "商品名称", "价格", "库存", "分类", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 80)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellClicked.connect(self._on_row_clicked)
        
        layout.addWidget(self.table, 1)
        
        self._load_all()
    
    def _load_all(self):
        self.current_products = self.product_store.get_all_products()
        self._refresh_table()
    
    def load_by_category(self, category: str):
        self.title.setText(f"📋 商品列表 - {category}")
        if category == "全部":
            self.current_products = self.product_store.get_all_products()
        else:
            self.current_products = [p for p in self.product_store.products if p.category == category]
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
                self.product_store.products,
                search_fields=["name", "description", "keywords"]
            )
            results = searcher.search(text, mode=mode)
            self.current_products = [r.item for r in results]
        self._refresh_table()
    
    def _refresh_table(self):
        self.table.setRowCount(len(self.current_products))
        
        for i, product in enumerate(self.current_products):
            self.table.setItem(i, 0, QTableWidgetItem(product.id))
            name_text = product.name[:25] + "..." if len(product.name) > 25 else product.name
            self.table.setItem(i, 1, QTableWidgetItem(name_text))
            self.table.setItem(i, 2, QTableWidgetItem(f"¥{product.price:.2f}"))
            stock_text = f"{product.stock}" if product.stock > 0 else "缺货"
            self.table.setItem(i, 3, QTableWidgetItem(stock_text))
            self.table.setItem(i, 4, QTableWidgetItem(product.category))
            self.table.setItem(i, 5, QTableWidgetItem("🗑️ 删除"))
    
    def _on_row_clicked(self, row: int, column: int):
        if 0 <= row < len(self.current_products):
            if column == 5:
                self._delete_product(row)
            else:
                self.product_selected.emit(self.current_products[row])
    
    def _add_product(self):
        """添加商品"""
        try:
            dialog = AddProductDialog(self.window())
            result = dialog.exec()
            if result:
                data = dialog.get_data()
                self.product_store.add_product(
                    name=data["name"],
                    price=data["price"],
                    category=data["category"],
                    description=data["description"],
                    specifications=data["specifications"],
                    stock=data["stock"],
                    keywords=data["keywords"]
                )
                self._load_all()
                self.product_added.emit()
                try:
                    from core.shared_data import KnowledgeStore
                    index_error = getattr(KnowledgeStore(), "last_vector_index_error", None)
                except Exception:
                    index_error = None

                if isinstance(index_error, dict) and index_error.get("type") == "dimension_mismatch":
                    InfoBar.success(
                        title="添加成功",
                        content="商品已添加（向量索引未更新）",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
                    InfoBar.warning(
                        title="需要重建索引",
                        content="检测到Embedding维度变化，请在知识库页面点击“重建向量索引”",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
                else:
                    InfoBar.success(
                        title="添加成功",
                        content="商品已添加，相关知识已同步到知识库",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
        except Exception as e:
            print(f"添加商品出错: {e}")
            InfoBar.error(
                title="添加失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def _delete_product(self, row: int):
        product = self.current_products[row]
        
        w = MessageBox(
            "确认删除", 
            f"确定要删除商品 {product.id} 吗？\n\n商品名称：{product.name}\n\n⚠️ 相关的知识条目也将被删除", 
            self
        )
        if w.exec():
            self.product_store.delete_product(product.id)
            self._load_all()
            self.product_deleted.emit(product.id)
            InfoBar.success(
                title="删除成功",
                content=f"商品 {product.id} 及相关知识已删除",
                parent=self,
                position=InfoBarPosition.TOP
            )


class ProductDetailPanel(QFrame):
    """商品详情面板"""
    
    product_updated = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(350)
        self.setStyleSheet("QFrame { border-left: 1px solid rgba(0,0,0,0.1); }")
        
        self.product_store = ProductStore()
        self.current_product = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        self.title = SubtitleLabel("📦 商品详情")
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
        self.edit_btn = PrimaryPushButton(FluentIcon.EDIT, "编辑商品")
        self.edit_btn.clicked.connect(self._edit_product)
        self.edit_btn.setEnabled(False)
        layout.addWidget(self.edit_btn)
    
    def _init_form(self):
        # 基本信息卡片
        info_card = CardWidget()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setSpacing(8)
        
        self.id_label = BodyLabel("🆔 ID：-")
        info_layout.addWidget(self.id_label)
        
        self.name_label = BodyLabel("📦 名称：-")
        self.name_label.setWordWrap(True)
        info_layout.addWidget(self.name_label)
        
        self.price_label = BodyLabel("💰 价格：-")
        info_layout.addWidget(self.price_label)
        
        self.stock_label = BodyLabel("📊 库存：-")
        info_layout.addWidget(self.stock_label)
        
        self.cat_label = BodyLabel("📁 分类：-")
        info_layout.addWidget(self.cat_label)
        
        self.keywords_label = BodyLabel("🏷️ 关键词：-")
        self.keywords_label.setWordWrap(True)
        info_layout.addWidget(self.keywords_label)
        
        self.content_layout.addWidget(info_card)
        
        # 规格卡片
        spec_card = CardWidget()
        spec_layout = QVBoxLayout(spec_card)
        spec_layout.setContentsMargins(12, 12, 12, 12)
        
        spec_title = BodyLabel("📋 规格参数")
        spec_title.setStyleSheet("font-weight: bold; color: #1890ff;")
        spec_layout.addWidget(spec_title)
        
        self.spec_label = BodyLabel("-")
        self.spec_label.setWordWrap(True)
        spec_layout.addWidget(self.spec_label)
        
        self.content_layout.addWidget(spec_card)
        
        # 描述卡片
        desc_card = CardWidget()
        desc_layout = QVBoxLayout(desc_card)
        desc_layout.setContentsMargins(12, 12, 12, 12)
        
        desc_title = BodyLabel("📝 商品描述")
        desc_title.setStyleSheet("font-weight: bold; color: #52c41a;")
        desc_layout.addWidget(desc_title)
        
        self.desc_label = BodyLabel("-")
        self.desc_label.setWordWrap(True)
        desc_layout.addWidget(self.desc_label)
        
        self.content_layout.addWidget(desc_card)
        self.content_layout.addStretch()
    
    def load_product(self, product: ProductItem):
        self.current_product = product
        self.edit_btn.setEnabled(True)
        
        self.title.setText(f"📦 商品详情 - {product.id}")
        self.id_label.setText(f"🆔 ID：{product.id}")
        self.name_label.setText(f"📦 名称：{product.name}")
        self.price_label.setText(f"💰 价格：¥{product.price:.2f}")
        
        stock_text = f"{product.stock}件" if product.stock > 0 else "缺货"
        self.stock_label.setText(f"📊 库存：{stock_text}")
        self.cat_label.setText(f"📁 分类：{product.category}")
        self.keywords_label.setText(f"🏷️ 关键词：{', '.join(product.keywords)}")
        
        if product.specifications:
            spec_lines = [f"  • {k}: {v}" for k, v in product.specifications.items()]
            self.spec_label.setText("\n".join(spec_lines))
        else:
            self.spec_label.setText("暂无规格参数")
        
        self.desc_label.setText(product.description)
    
    def _edit_product(self):
        """编辑商品"""
        if not self.current_product:
            return
        
        try:
            dialog = AddProductDialog(self.window(), self.current_product)
            result = dialog.exec()
            if result:
                data = dialog.get_data()
                self.product_store.update_product(
                    self.current_product.id,
                    name=data["name"],
                    price=data["price"],
                    category=data["category"],
                    description=data["description"],
                    specifications=data["specifications"],
                    stock=data["stock"],
                    keywords=data["keywords"]
                )
                # 重新加载商品
                updated = self.product_store.get_product_by_id(self.current_product.id)
                if updated:
                    self.load_product(updated)
                self.product_updated.emit()
                try:
                    from core.shared_data import KnowledgeStore
                    index_error = getattr(KnowledgeStore(), "last_vector_index_error", None)
                except Exception:
                    index_error = None

                if isinstance(index_error, dict) and index_error.get("type") == "dimension_mismatch":
                    InfoBar.success(
                        title="更新成功",
                        content="商品信息已更新（向量索引未更新）",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
                    InfoBar.warning(
                        title="需要重建索引",
                        content="检测到Embedding维度变化，请在知识库页面点击“重建向量索引”",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
                else:
                    InfoBar.success(
                        title="更新成功",
                        content="商品信息已更新，知识库已同步",
                        parent=self,
                        position=InfoBarPosition.TOP
                    )
        except Exception as e:
            print(f"编辑商品出错: {e}")
            InfoBar.error(
                title="更新失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )


class ProductToolbar(QFrame):
    """底部工具栏"""
    
    sync_completed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setStyleSheet("""
            ProductToolbar { 
                border: none;
                border-top: 1px solid rgba(0,0,0,0.1);
                background-color: #FAFAFA;
            }
        """)
        
        self.product_store = ProductStore()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(16)
        
        # 商品统计
        self.stats_label = BodyLabel(f"🛍️ 共 {len(ProductStore().products)} 个商品")
        self.stats_label.setStyleSheet("color: gray;")
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        
        # 同步按钮
        self.sync_btn = PrimaryPushButton(FluentIcon.SYNC, "同步所有商品到知识库")
        self.sync_btn.clicked.connect(self._sync_all)
        layout.addWidget(self.sync_btn)
    
    def _sync_all(self):
        """同步所有商品到知识库"""
        self.sync_btn.setEnabled(False)
        self.sync_btn.setText("同步中...")
        
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._do_sync)
    
    def _do_sync(self):
        """执行同步"""
        try:
            success, fail = self.product_store.sync_all_to_knowledge()
            if fail == 0:
                InfoBar.success(
                    title="同步成功",
                    content=f"已将 {success} 个商品同步到知识库",
                    parent=self,
                    position=InfoBarPosition.TOP
                )
            else:
                InfoBar.warning(
                    title="部分同步成功",
                    content=f"成功 {success} 个，失败 {fail} 个",
                    parent=self,
                    position=InfoBarPosition.TOP
                )
            self.sync_completed.emit()
        except Exception as e:
            print(f"同步商品出错: {e}")
            InfoBar.error(
                title="同步失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
        finally:
            self.sync_btn.setEnabled(True)
            self.sync_btn.setText("同步所有商品到知识库")
    
    def refresh_stats(self):
        """刷新统计"""
        self.stats_label.setText(f"🛍️ 共 {len(ProductStore().products)} 个商品")


class ProductInterface(QWidget):
    """商品管理界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("product_interface")
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        self.category_panel = ProductCategoryPanel()
        self.category_panel.category_selected.connect(self._on_category_selected)
        content_layout.addWidget(self.category_panel)
        
        self.product_list_panel = ProductListPanel()
        self.product_list_panel.product_selected.connect(self._on_product_selected)
        self.product_list_panel.product_deleted.connect(self._on_product_changed)
        self.product_list_panel.product_added.connect(self._on_product_changed)
        content_layout.addWidget(self.product_list_panel, 1)
        
        self.detail_panel = ProductDetailPanel()
        self.detail_panel.product_updated.connect(self._on_product_changed)
        content_layout.addWidget(self.detail_panel)
        
        layout.addWidget(content, 1)
        
        self.toolbar = ProductToolbar()
        layout.addWidget(self.toolbar)
    
    def _on_category_selected(self, category: str):
        self.product_list_panel.load_by_category(category)
    
    def _on_product_selected(self, product: ProductItem):
        self.detail_panel.load_product(product)
    
    def _on_product_changed(self, *args):
        """商品变更后刷新"""
        self.category_panel.refresh()
        self.toolbar.refresh_stats()
        self.product_list_panel._load_all()
