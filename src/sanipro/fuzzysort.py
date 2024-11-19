import heapq
import itertools
import logging
import random
from abc import ABC, abstractmethod
from difflib import SequenceMatcher

from . import utils
from .abc import MutablePrompt, Prompt

logger = logging.getLogger(__name__)

available = ("naive", "greedy", "mst")


# 類似度計算の戦略インターフェース
class SimilarityStrategy(ABC):

    @abstractmethod
    def calculate_similarity(self, word1: str, word2: str) -> float:
        """2つの文字列の類似度を計算する"""


try:
    import Levenshtein  # type: ignore

    # Levenshtein距離を利用した類似度計算
    class LevenshteinSimilarity(SimilarityStrategy):

        def calculate_similarity(self, word1: str, word2: str) -> float:
            distance = Levenshtein.distance(word1, word2)
            max_len = max(len(word1), len(word2))
            return 1 - (distance / max_len)

except ImportError:
    pass


# SequenceMatcherを利用した類似度計算
class SequenceMatcherSimilarity(SimilarityStrategy):

    def calculate_similarity(self, word1: str, word2: str) -> float:
        return SequenceMatcher(None, word1, word2).ratio()


# 並べ替えの戦略インターフェース
class ReordererStrategy(ABC):
    @abstractmethod
    def __init__(self, strategy: SimilarityStrategy):
        pass

    @abstractmethod
    def find_optimal_order(self, words: Prompt) -> MutablePrompt:
        """2つの文字列の類似度を計算する"""


# 並べ替えを行うクラス
class NaiveReorderer(ReordererStrategy):

    def __init__(self, strategy: SimilarityStrategy):
        self.strategy = strategy

    def find_optimal_order(self, words: Prompt) -> MutablePrompt:
        best_order = tuple()
        best_score = float("-inf")

        # 全順列を試して最もスコアが高い順序を見つける
        for permutation in itertools.permutations(words):
            total_score = sum(
                self.strategy.calculate_similarity(
                    permutation[i].name, permutation[i + 1].name
                )
                for i in range(len(permutation) - 1)
            )
            if total_score > best_score:
                best_score = total_score
                best_order = permutation

        return list(best_order)


# 貪欲法による並べ替えクラス
class GreedyReorderer(ReordererStrategy):

    def __init__(self, strategy: SimilarityStrategy):
        self.strategy = strategy

    def find_optimal_order(self, words: Prompt) -> MutablePrompt:
        # シャッフルしてランダムな初期要素を選ぶ
        words = list(words[:])
        random.shuffle(words)
        result = [words.pop()]

        # 貪欲法で最も似ている単語を選び続ける
        while words:
            last_word = result[-1].name
            next_word = max(
                words,
                key=lambda w: self.strategy.calculate_similarity(last_word, w.name),
            )
            result.append(next_word)
            words.remove(next_word)

        return result


Edge = tuple[int, int]

WeightedEdge = tuple[float, Edge]
WeightedVertice = tuple[float, int]

AdjacencyList = list[list[int]]
AdjacencyListWeighted = list[list[WeightedVertice]]


# MSTによる並べ替え戦略
class MSTReorderer(ReordererStrategy):
    def __init__(self, strategy: SimilarityStrategy):
        self.strategy = strategy

    def _convert_to_adjacency_list(
        self, edges: list[WeightedEdge], num_vertices: int
    ) -> AdjacencyListWeighted:
        # 隣接リストを初期化
        graph = [[] for _ in range(num_vertices)]

        # グラフの構築（無向グラフ）
        for weight, (u, v) in edges:
            graph[u].append((weight, v))
            graph[v].append((weight, u))

        return graph

    def find_optimal_order(self, words: Prompt) -> MutablePrompt:
        words = list(words[:])
        n = len(words)

        # 完全グラフのエッジリストを構築
        edges: list[WeightedEdge] = []
        for i in range(n):
            for j in range(i + 1, n):
                similarity = self.strategy.calculate_similarity(
                    words[i].name, words[j].name
                )
                weight = 1 - similarity  # 類似度が高いほど重みは低くする
                edges.append((weight, (i, j)))

        # 最小全域木の構築（Prim'sアルゴリズムを使用）
        mst = self._build_mst(n, self._convert_to_adjacency_list(edges, n))

        # 最小全域木をDFSで探索し、順序を決定
        visited = [False] * n
        order = []

        def dfs(node):
            visited[node] = True
            order.append(words[node])
            for neighbor in mst[node]:
                if not visited[neighbor]:
                    dfs(neighbor)

        dfs(0)  # 0番目の頂点から探索開始
        return order

    def _build_mst(self, n: int, graph: AdjacencyListWeighted) -> AdjacencyList:
        # 最小全域木のエッジを格納するリスト
        mst_edges: list[Edge] = []

        # 訪問済みノードの集合
        visited = set()
        # 最小ヒープ（weight, from_node, to_node）
        min_heap = []

        # 開始ノードを0とする
        start_node = 0
        visited.add(start_node)

        # 開始ノードから到達可能なエッジをヒープに追加
        for weight, neighbor in graph[start_node]:
            heapq.heappush(min_heap, (weight, start_node, neighbor))

        # Prim法のメインループ
        while min_heap and len(visited) < n:
            weight, u, v = heapq.heappop(min_heap)

            # ノードvが訪問済みならスキップ
            if v in visited:
                continue

            # エッジ (u, v) を最小全域木に追加
            mst_edges.append((u, v))
            visited.add(v)

            # 新たに訪問したノードからのエッジをヒープに追加
            for next_weight, next_node in graph[v]:
                if next_node not in visited:
                    heapq.heappush(min_heap, (next_weight, v, next_node))

        mst: AdjacencyList = [[] for _ in range(n)]

        # グラフの構築（無向グラフ）
        for u, v in mst_edges:
            mst[u].append(v)
            mst[v].append(u)

        return mst


funcs = (NaiveReorderer, GreedyReorderer, MSTReorderer)


def apply_from(keyword: str) -> type[ReordererStrategy]:
    try:
        matcher = utils.ModuleMatcher(available, funcs)
        matched: type[ReordererStrategy] = matcher.match(keyword)
        return matched
    except NotImplementedError:
        raise NotImplementedError(f"no matched fuzzysort law for {keyword!r}")
