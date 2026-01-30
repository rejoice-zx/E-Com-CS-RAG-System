# -*- coding: utf-8 -*-
"""
设置对话框模块 - 使用 Fluent Widgets
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QFormLayout
)
from PySide6.QtCore import Qt, Signal

import os

from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel,
    SpinBox, LineEdit, ComboBox, Slider,
    PrimaryPushButton, PushButton, PasswordLineEdit,
    CardWidget
)

from core.config import Config


class SettingsDialog(MessageBoxBase):
    """设置对话框"""
    
    settings_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = Config()
        
        self.titleLabel = SubtitleLabel("设置")
        self.viewLayout.addWidget(self.titleLabel)
        
        self._init_ui()
        self._load_settings()
        
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")
        
        self.yesButton.clicked.connect(self._save_settings)
        
        self.widget.setMinimumWidth(450)
    
    def _init_ui(self):
        """初始化UI"""
        # API设置
        api_card = CardWidget()
        api_layout = QVBoxLayout(api_card)
        api_layout.setContentsMargins(16, 16, 16, 16)
        api_layout.setSpacing(12)
        
        api_title = BodyLabel("🔗 API配置")
        api_title.setStyleSheet("font-weight: bold;")
        api_layout.addWidget(api_title)
        
        # API地址
        url_row = QHBoxLayout()
        url_row.addWidget(BodyLabel("API地址:"))
        self.api_url = LineEdit()
        self.api_url.setPlaceholderText("https://api.siliconflow.cn/v1")
        url_row.addWidget(self.api_url, 1)
        api_layout.addLayout(url_row)
        
        # API密钥
        key_row = QHBoxLayout()
        key_row.addWidget(BodyLabel("API密钥:"))
        self.api_key = PasswordLineEdit()
        self.api_key.setPlaceholderText("sk-...")
        key_row.addWidget(self.api_key, 1)
        api_layout.addLayout(key_row)
        
        # 模型 - 硅基流动支持的模型
        model_row = QHBoxLayout()
        model_row.addWidget(BodyLabel("模型:"))
        self.model_combo = ComboBox()
        self.model_combo.addItems([
            "Qwen/Qwen3-8B",
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            "THUDM/GLM-4-9B-0414"
        ])
        model_row.addWidget(self.model_combo)
        model_row.addStretch()
        api_layout.addLayout(model_row)
        
        self.viewLayout.addWidget(api_card)
        
        # 高级设置
        adv_card = CardWidget()
        adv_layout = QVBoxLayout(adv_card)
        adv_layout.setContentsMargins(16, 16, 16, 16)
        adv_layout.setSpacing(12)
        
        adv_title = BodyLabel("⚙️ 高级设置")
        adv_title.setStyleSheet("font-weight: bold;")
        adv_layout.addWidget(adv_title)
        
        # 最大令牌
        tokens_row = QHBoxLayout()
        tokens_row.addWidget(BodyLabel("最大令牌:"))
        self.max_tokens = SpinBox()
        self.max_tokens.setRange(256, 8192)
        self.max_tokens.setValue(2048)
        self.max_tokens.setSingleStep(256)
        tokens_row.addWidget(self.max_tokens)
        tokens_row.addStretch()
        adv_layout.addLayout(tokens_row)
        
        # 温度
        temp_row = QHBoxLayout()
        temp_row.addWidget(BodyLabel("温度:"))
        self.temp_slider = Slider(Qt.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_slider.setValue(70)
        self.temp_slider.setFixedWidth(150)
        temp_row.addWidget(self.temp_slider)
        self.temp_label = BodyLabel("0.7")
        self.temp_label.setFixedWidth(30)
        self.temp_slider.valueChanged.connect(
            lambda v: self.temp_label.setText(f"{v/100:.1f}")
        )
        temp_row.addWidget(self.temp_label)
        temp_row.addStretch()
        adv_layout.addLayout(temp_row)
        
        self.viewLayout.addWidget(adv_card)
    
    def _load_settings(self):
        """加载设置"""
        self.api_url.setText(self.config.get("api_base_url", "", include_env=False))
        configured_key = bool(self.config.get("api_key", "", include_env=True))
        self.api_key.setText("")
        self.api_key.setPlaceholderText("已配置（不显示）" if configured_key else "sk-...")
        self.model_combo.setCurrentText(self.config.get("model_name", "gpt-3.5-turbo"))
        
        self.max_tokens.setValue(self.config.get("max_tokens", 2048))
        temp = int(self.config.get("temperature", 0.7) * 100)
        self.temp_slider.setValue(temp)
        self.temp_label.setText(f"{temp/100:.1f}")
    
    def _save_settings(self):
        """保存设置"""
        settings: dict = {
            "api_base_url": self.api_url.text().strip(),
            "model_name": self.model_combo.currentText().strip(),
            "max_tokens": self.max_tokens.value(),
            "temperature": self.temp_slider.value() / 100
        }

        api_key = self.api_key.text().strip()
        if api_key:
            self.config.set("api_key", api_key)
            self.api_key.setText("")
            self.api_key.setPlaceholderText("已配置（已保存）")
        
        self.config.update(settings)
        self.settings_changed.emit()
