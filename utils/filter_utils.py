"""内容过滤工具 - 过滤不文明语言"""
import re

# 脏话词库（中文常见脏话）
DIRTY_WORDS = [
    # 人身攻击类
    "傻逼", "傻B", "sb", "SB",
    "操", "草", "艹",
    "你妈", "你娘", "你爸", "你爹",
    "妈逼", "妈B", "MB", "mB",
    "狗日的", "狗娘养的",
    "去死", "滚蛋", "滚",
    "垃圾", "废物", "脑残", "智障",
    # 低俗词汇
    "屌", "鸡巴", "JB", "jb",
    "逼", "B", "b",
    "屁", "屎", "尿",
    # 其他不文明用语
    "卧槽", "我靠", "靠",
    "他妈的", "他妈",
    "变态", "猥琐", "恶心",
]

# 替换词
CLEAN_WORDS = [
    "傻瓜", "傻瓜", "傻瓜", "傻瓜",
    "哎", "哎", "哎",
    "你家人", "你家人", "你家人", "你家人",
    "糟糕", "糟糕", "糟糕", "糟糕",
    "讨厌的", "讨厌的",
    "走开", "走开", "走开",
    "差劲", "差劲", "糊涂", "糊涂",
    "厉害", "厉害", "厉害", "厉害",
    "尴尬", "尴尬", "尴尬",
    "事", "屎", "尿",
    "哇", "哇", "哇",
    "有点", "有点",
    "奇怪", "奇怪", "不好",
]

def filter_dirty_words(text: str) -> str:
    """过滤文本中的不文明语言
    
    Args:
        text: 原始文本
        
    Returns:
        过滤后的文本
    """
    if not text:
        return text
        
    result = text
    
    # 使用正则替换脏话
    for dirty, clean in zip(DIRTY_WORDS, CLEAN_WORDS):
        # 创建正则模式，支持部分匹配
        pattern = re.escape(dirty)
        result = re.sub(pattern, clean, result, flags=re.IGNORECASE)
    
    return result

def is_clean(text: str) -> bool:
    """检查文本是否包含脏话
    
    Args:
        text: 待检查文本
        
    Returns:
        True表示干净，False表示包含脏话
    """
    for dirty in DIRTY_WORDS:
        if dirty.lower() in text.lower():
            return False
    return True

def normalize_text(text: str) -> str:
    """文本规范化处理：过滤脏话并清理格式
    
    Args:
        text: 原始文本
        
    Returns:
        规范化后的文本
    """
    # 过滤脏话
    result = filter_dirty_words(text)
    
    # 清理多余空格和换行
    result = ' '.join(result.split())
    
    # 确保以句号结尾
    if result and not result.endswith(('。', '！', '？', '...')):
        result += '。'
    
    return result