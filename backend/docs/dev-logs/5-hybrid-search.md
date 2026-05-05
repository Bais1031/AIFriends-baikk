# 混合检索（Hybrid Search）实现文档

## 概述

本文档描述了 AIFriends 项目中 RAG 检索策略的升级：从纯向量检索升级为**向量检索 + BM25 关键词检索**的混合检索方案，提升检索准确率。

## 原有实现的问题

### 纯向量检索的局限

原实现仅使用向量相似度检索：

```python
docs = vector_db.similarity_search(query, k=3)
```

存在以下问题：

1. **关键词丢失**：向量检索关注语义相似性，对精确关键词匹配较弱。例如查询 "API Key" 时，语义相近的文档可能排名靠前，但真正包含 "API Key" 关键词的文档反而被遗漏。
2. **领域术语不敏感**：专业术语、产品名称等专有名词在语义空间中可能不够突出，导致检索偏离。
3. **短查询不稳定**：用户输入较短时，向量表示的语义信息不足，检索结果波动大。

## 混合检索原理

### 核心思路

混合检索将两种互补的检索方式融合：

| 检索方式 | 优势 | 劣势 |
|---------|------|------|
| 向量检索 | 理解语义相似性，处理同义词、改写 | 精确关键词匹配弱 |
| BM25 关键词检索 | 精确匹配关键词，对专有名词敏感 | 无法理解语义 |

### 融合公式

```
最终分数 = α × 向量分数 + (1-α) × 关键词分数
```

- `α` 默认值 0.7，表示 70% 权重给语义检索，30% 给关键词检索
- 可根据实际场景调整：领域术语多的场景降低 α，语义理解多的场景提高 α

### BM25 算法

BM25（Best Matching 25）是经典的全文检索算法，基于以下因素计算相关性：

1. **词频（TF）**：关键词在文档中出现的次数越多，相关性越高
2. **逆文档频率（IDF）**：关键词在所有文档中越罕见，区分度越高
3. **文档长度归一化**：避免长文档因词频高而获得不公平优势

公式简化表示：

```
BM25(D, Q) = Σ IDF(qi) × (f(qi, D) × (k1 + 1)) / (f(qi, D) + k1 × (1 - b + b × |D| / avgdl))
```

其中 `qi` 是查询中的每个词，`f(qi, D)` 是词频，`|D|` 是文档长度，`avgdl` 是平均文档长度。

### 中文分词

BM25 基于词袋模型，需要对文本进行分词。本项目使用 **jieba** 进行中文分词：

```python
import jieba
tokens = list(jieba.cut("API Key 如何获取"))
# ['API', ' ', 'Key', ' ', '如何', '获取']
```

jieba 采用基于前缀词典的分词算法，支持：
- 精确模式：最精确的分词，适合文本分析
- 全模式：扫描所有可能的词组，速度最快
- 搜索引擎模式：在精确模式基础上对长词再次切分

## 实现细节

### 切分优化

在升级混合检索之前，先优化了文档切分参数：

```python
# 原参数
RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

# 优化后
RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
)
```

| 参数 | 原值 | 新值 | 说明 |
|------|------|------|------|
| chunk_size | 500 | 800 | 更大的切分块保留更完整的上下文 |
| chunk_overlap | 50 | 100 | 更多重叠减少边界信息丢失 |
| separators | 默认 | 中文分隔符 | 按中文标点优先切分，保持语义完整 |

### 混合检索实现

核心代码位于 `web/documents/utils/hybrid_search.py`：

```python
def hybrid_search(vector_db, query, k=3, alpha=0.7):
    # 1. 向量检索：获取 2k 个候选结果
    vector_docs = vector_db.similarity_search_with_score(query, k=k * 2)

    # 2. BM25 关键词检索：对候选结果计算关键词分数
    corpus = [doc.page_content for doc, _ in vector_docs]
    tokenized_corpus = [list(jieba.cut(doc)) for doc in corpus]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(list(jieba.cut(query)))

    # 3. 分数归一化 + 加权融合
    #    向量距离转为相似度（距离越小越好 → 1 - 归一化距离）
    #    BM25 分数归一化到 0-1
    final_score = alpha * norm_vector + (1 - alpha) * norm_bm25

    # 4. 按融合分数排序，返回 top-k
```

### 调用方式

在 `graph.py` 的 `search_knowledge_base` 工具中：

```python
from web.documents.utils.hybrid_search import hybrid_search

docs = hybrid_search(vector_db, query, k=3)
```

## 新增依赖

| 包 | 版本 | 用途 |
|----|------|------|
| jieba | 0.42.1 | 中文分词 |
| rank-bm25 | 0.2.2 | BM25 算法实现 |
| pylance | 4.0.0 | LanceDB 底层存储支持 |

## 文件变更

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `web/documents/utils/hybrid_search.py` | 新增 | 混合检索工具类 |
| `web/documents/utils/insert_documents.py` | 修改 | 优化切分参数 |
| `web/views/friend/message/chat/graph.py` | 修改 | 使用混合检索替代纯向量检索 |
| `requirements.txt` | 修改 | 新增依赖 |

## 配置建议

### alpha 权重调整

| 场景 | 建议值 | 说明 |
|------|--------|------|
| 通用问答 | 0.7（默认） | 平衡语义和关键词 |
| 精确术语查询 | 0.4-0.5 | 更侧重关键词匹配 |
| 开放性对话 | 0.8-0.9 | 更侧重语义理解 |

### k 值调整

- `k=3`：适合快速回答，上下文精简
- `k=5`：适合需要更多参考信息的复杂问题

---
**文档版本**: 1.0
**更新日期**: 2026-04-22
