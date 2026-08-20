# -*- coding: utf-8 -*-
"""
UI 设计系统变量与调色板定义 (Design Tokens)
遵循 AKTokens 规范：主色珊瑚粉 (#F25378)，支持 Light / Dark 双主题。
"""

DARK_THEME_TOKENS = {
    # 背景与表面
    "bg_window": "#18191c",
    "bg_card": "#222429",
    "bg_card_head": "#2a2d34",
    "bg_input": "#1d1f24",
    "bg_output": "#1c1f24",
    "bg_hover": "#2e323b",
    "bg_table_alt": "#1f2126",
    "bg_preview": "#121316",
    
    # 描边与分割线
    "border_light": "#2e323b",
    "border_normal": "#383c46",
    "border_hover": "#4f5563",
    "border_focus": "#F25378",
    
    # 文本阶梯
    "text_primary": "#f0f2f5",
    "text_regular": "#d3d6de",
    "text_secondary": "#8c92a4",
    "text_placeholder": "#5d6373",
    "text_output": "#f0f2f5",
    
    # 品牌主色 (Coral Pink 珊瑚粉)
    "accent_primary": "#F25378",
    "accent_primary_hover": "#D83F66",
    "accent_primary_active": "#BF2F53",
    "accent_primary_disabled": "#5c2432",
    "accent_tint": "#382329",
    
    # 功能状态色
    "accent_success": "#67c23a",
    "accent_success_hover": "#85ce61",
    "accent_warning": "#e6a23c",
    "accent_warning_hover": "#ebb563",
    "accent_danger": "#f56c6c",
    "accent_danger_hover": "#f78989",
    "accent_info": "#606266",
    "accent_info_hover": "#73767a",
    
    # 打轴高亮色
    "highlight_active_row": "#382329",
    "highlight_active_text": "#F25378",
    "highlight_karaoke_played": "#F25378",
    "highlight_karaoke_active": "#ff7597",
    "highlight_karaoke_unplayed": "#686f80",
    
    "shadow_color": "rgba(0, 0, 0, 0.4)",
}

LIGHT_THEME_TOKENS = {
    # 背景与表面 (奶油底 + 纯白卡片)
    "bg_window": "#FAF6F1",
    "bg_card": "#FFFFFF",
    "bg_card_head": "#F7F2EB",
    "bg_input": "#FFFFFF",
    "bg_output": "#FFFFFF",
    "bg_hover": "#F5ECE1",
    "bg_table_alt": "#FBF8F4",
    "bg_preview": "#FAF6F1",
    
    # 描边与分割线
    "border_light": "#ECE6E0",
    "border_normal": "#E0D7CE",
    "border_hover": "#D0C4B8",
    "border_focus": "#F25378",
    
    # 文本阶梯
    "text_primary": "#232020",
    "text_regular": "#423D3A",
    "text_secondary": "#6E6864",
    "text_placeholder": "#A8A09A",
    "text_output": "#232020",
    
    # 品牌主色 (Coral Pink 珊瑚粉)
    "accent_primary": "#F25378",
    "accent_primary_hover": "#D83F66",
    "accent_primary_active": "#BF2F53",
    "accent_primary_disabled": "#F9A8BC",
    "accent_tint": "#FDECEF",
    
    # 功能状态色
    "accent_success": "#52c41a",
    "accent_success_hover": "#73d13d",
    "accent_warning": "#faad14",
    "accent_warning_hover": "#ffc53d",
    "accent_danger": "#ff4d4f",
    "accent_danger_hover": "#ff7875",
    "accent_info": "#8c8c8c",
    "accent_info_hover": "#bfbfbf",
    
    # 打轴高亮色
    "highlight_active_row": "#FDECEF",
    "highlight_active_text": "#F25378",
    "highlight_karaoke_played": "#F25378",
    "highlight_karaoke_active": "#D83F66",
    "highlight_karaoke_unplayed": "#8c92a4",
    
    "shadow_color": "rgba(35, 32, 32, 0.06)",
}
