# 功能开发文档：模拟训练模式

## 功能概述
不消耗真实筹码的练习模式，包含详细错误分析

## 需求分析
- 无筹码消耗练习
- 策略建议系统
- 错误分析功能
- 技能提升指导

## 训练模式设计

### 模式分类
#### 新手指引模式
- 基础规则讲解
- 操作提示
- 逐步引导

#### 策略练习模式
- 针对性场景训练
- 策略选择指导
- 统计数据反馈

#### 高级技巧模式
- 特殊情况处理
- 心理战术练习
- 多手牌策略

### 训练场景
- 特定牌况模拟
- 高难度场景
- 随机事件训练
- 时间压力测试

## 技术实现

### 训练会话数据结构
```python
@dataclass
class TrainingSession:
    session_id: str
    player_id: str
    mode: str  # 'beginner', 'strategy', 'advanced'
    scenario: str  # 特定训练场景
    games_played: int = 0
    correct_decisions: int = 0
    learning_focus: list[str] = field(default_factory=list)  # 当前学习重点
    improvement_areas: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

@dataclass
class TrainingAnalysis:
    session_id: str
    decision_history: list[dict]  # 记录每步决策
    ai_recommendation: str
    player_choice: str
    correctness: bool
    explanation: str
    timestamp: float
```

### AI策略建议
1. 根据当前牌况给出推荐策略
2. 解释推荐理由
3. 显示其他选择的后果
4. 提供改进建议

### 错误分析算法
- 识别常见错误模式
- 分析决策偏差
- 提供针对性建议
- 追踪改进进度

## 用户界面
- `/training start` 开始训练
- 训练建议面板
- 错误分析报告
- 进度统计图表

## 教学功能
- 规则详解
- 策略教程
- 视频演示
- FAQ解答

## 成果评估
- 正确率统计
- 改进幅度测量
- 技能等级提升
- 建议转换到实战

## 测试要点
- 建议准确性
- 分析深度
- 用户体验友好度
- 学习效果评估