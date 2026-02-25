# 功能开发文档：牌型收藏册

## 功能概述
收集特殊的牌型组合（如五龙、六龙、清一色等），解锁特殊称号

## 需求分析
- 识别并记录特殊牌型
- 展示已收集和未收集的牌型
- 解锁特殊称号和奖励
- 支持分享已收集的稀有牌型

## 技术实现

### 特殊牌型定义
```python
# 在 game_logic.py 中添加
SPECIAL_HANDS = {
    "five_dragons": {"name": "五龙", "description": "五张牌总点数不超过21点"},
    "six_dragons": {"name": "六龙", "description": "六张牌总点数不超过21点"},
    "blackjack_triple": {"name": "三倍黑杰克", "description": "连续三次获得黑杰克"},
    "flush": {"name": "同花", "description": "所有牌同一种花色"},
    "straight": {"name": "顺子", "description": "连续数字的牌"},
    "pair_plus": {"name": "对子王", "description": "连续获得五次对子"},
}
```

### 数据模型修改
```python
@dataclass
class CardCollection:
    user_id: str
    collected_hands: list[str] = field(default_factory=list)
    unlock_date: dict[str, float] = field(default_factory=dict)
```

### 牌型检测算法
1. 游戏过程中实时检测特殊牌型
2. 符合条件时记录到收藏册
3. 检查是否解锁新称号
4. 发送解锁通知

### 界面设计
- 收藏册界面显示所有牌型及其状态
- 已解锁牌型显示解锁时间和特殊效果
- 未解锁牌型显示获取条件

## 用户界面
- `/collection` 命令查看收藏册
- 特殊牌型达成时发送解锁动画
- 可分享特定牌型给好友

## 测试要点
- 特殊牌型检测准确性
- 收藏状态正确保存
- 解锁通知正常发送
- 称号系统正确应用