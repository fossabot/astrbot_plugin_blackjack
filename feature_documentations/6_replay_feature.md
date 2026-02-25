# 功能开发文档：录像回放功能

## 功能概述
保存精彩对局录像，可以随时回顾和分享

## 需求分析
- 录制完整的游戏过程
- 保存游戏关键数据
- 支持快进、暂停、慢放
- 可分享到社区

## 录像系统设计

### 录像触发条件
- 高倍率胜利
- 特殊牌型出现
- 精彩操作
- 用户主动录制

### 录像数据结构
```python
@dataclass
class GameAction:
    timestamp: float
    player_id: str
    action: str  # 'hit', 'stand', 'double', 'split', 'surrender', 'bet'
    cards_drawn: list[str] = field(default_factory=list)
    current_hand_value: int = 0

@dataclass
class GameReplay:
    replay_id: str
    game_data: dict
    actions: list[GameAction]
    result: dict
    recorded_at: float
    recording_player: str
    tags: list[str] = field(default_factory=list)  # 如['high_stakes', 'amazing_win']
```

## 技术实现

### 录像录制机制
1. 游戏开始时初始化录像对象
2. 每个操作发生时记录到动作序列
3. 游戏结束后添加最终结果
4. 根据预设条件自动保存

### 存储方案
- 使用数据库存储录像元数据
- 压缩存储详细动作序列
- 支持云存储录像文件

### 播放功能
- 时间轴拖拽
- 播放速度控制（0.5x, 1x, 2x, 4x）
- 关键节点标记
- 注释功能

## 用户界面
- `/replay save` 手动保存当前游戏
- `/replay list` 查看保存的录像
- `/replay watch <id>` 播放指定录像
- 录像播放器界面

## 社区分享
- 录像上传至社区
- 点赞和评论系统
- 精选推荐
- 录像分类标签

## 测试要点
- 录像完整性
- 播放流畅性
- 存储空间效率
- 回放准确性