"""
Semantic Model Calibration & Evidence Benchmark (Round 2 - Task T2).

Evaluates candidate SentenceTransformer models on an in-code labeled dataset:
- Code: 10 plagiarized pairs (2+ transforms: renaming, for<->while, function reordering,
  comment rewriting, extract-helper) and 10 unrelated pairs across Python, Java, and JavaScript.
- English Text: 8 academic paraphrase pairs and 8 unrelated pairs (each >= 60 words).
- Arabic Text: 8 Modern Standard Arabic paraphrase pairs (synonym substitution + clause
  reordering) and 8 unrelated pairs (each >= 60 words).

Computes per-domain / per-model:
- Mean, Min, Max cosine similarity for plagiarized (positive) and unrelated (negative) pairs
- Margin = min(plagiarized) - max(unrelated)
- Pairwise ROC-AUC (computed directly without scikit-learn)
- Recommended calibration floor = round(mean(unrelated), 2)

Writes full results to `calibration_results.md` in the project root.
"""

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plagiarism_engine.config import load_project_env

load_project_env()

from sentence_transformers import SentenceTransformer


# ============================================================================
# 1. IN-CODE LABELED DATASET
# ============================================================================

# --- CODE: 10 Plagiarized Pairs (Python x4, Java x3, JavaScript x3) ---
CODE_PLAGIARIZED_PAIRS: List[Tuple[str, str]] = [
    # 1. Python: Dijkstra shortest path (renaming + for->while + helper extraction + comments)
    (
        """# Compute shortest paths from start_node in a weighted adjacency graph
import heapq

def shortest_path_dijkstra(graph_adj, start_node):
    distances = {node: float('inf') for node in graph_adj}
    distances[start_node] = 0.0
    priority_queue = [(0.0, start_node)]
    visited = set()

    while priority_queue:
        current_dist, current_vertex = heapq.heappop(priority_queue)
        if current_vertex in visited:
            continue
        visited.add(current_vertex)
        for neighbor, weight in graph_adj[current_vertex].items():
            candidate_dist = current_dist + weight
            if candidate_dist < distances[neighbor]:
                distances[neighbor] = candidate_dist
                heapq.heappush(priority_queue, (candidate_dist, neighbor))
    return distances
""",
        """import heapq

def _init_cost_map(network, origin):
    costs = {}
    keys = list(network.keys())
    idx = 0
    while idx < len(keys):
        costs[keys[idx]] = float('inf')
        idx += 1
    costs[origin] = 0.0
    return costs

def find_minimum_routes(network, origin):
    costs = _init_cost_map(network, origin)
    heap = [(0.0, origin)]
    seen_nodes = set()
    while len(heap) > 0:
        cost_so_far, u = heapq.heappop(heap)
        if u not in seen_nodes:
            seen_nodes.add(u)
            items = list(network[u].items())
            k = 0
            while k < len(items):
                v, edge_w = items[k]
                new_cost = cost_so_far + edge_w
                if new_cost < costs[v]:
                    costs[v] = new_cost
                    heapq.heappush(heap, (new_cost, v))
                k += 1
    return costs
""",
    ),
    # 2. Python: Merge sort implementation (function reordering + renaming + for->while)
    (
        """# Recursive merge sort on a list of comparable elements
def merge_sorted_halves(left_half, right_half):
    merged = []
    i = 0
    j = 0
    while i < len(left_half) and j < len(right_half):
        if left_half[i] <= right_half[j]:
            merged.append(left_half[i])
            i += 1
        else:
            merged.append(right_half[j])
            j += 1
    merged.extend(left_half[i:])
    merged.extend(right_half[j:])
    return merged

def merge_sort(values):
    if len(values) <= 1:
        return list(values)
    mid_idx = len(values) // 2
    left_sorted = merge_sort(values[:mid_idx])
    right_sorted = merge_sort(values[mid_idx:])
    return merge_sorted_halves(left_sorted, right_sorted)
""",
        """def divide_and_sort(seq):
    n = len(seq)
    if n <= 1:
        return list(seq)
    split = n // 2
    part_a = divide_and_sort(seq[:split])
    part_b = divide_and_sort(seq[split:])
    return _combine_runs(part_a, part_b)

def _combine_runs(run_a, run_b):
    out = []
    p1, p2 = 0, 0
    while p1 < len(run_a) and p2 < len(run_b):
        if run_a[p1] <= run_b[p2]:
            out.append(run_a[p1])
            p1 += 1
        else:
            out.append(run_b[p2])
            p2 += 1
    for rem_a in run_a[p1:]:
        out.append(rem_a)
    for rem_b in run_b[p2:]:
        out.append(rem_b)
    return out
""",
    ),
    # 3. Python: LRU Cache with OrderedDict (renaming + method reordering + comment removal)
    (
        """from collections import OrderedDict

class LRUCacheStorage:
    # Fixed-capacity least-recently-used cache
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.entries = OrderedDict()

    def get_value(self, key: str):
        if key not in self.entries:
            return None
        self.entries.move_to_end(key)
        return self.entries[key]

    def put_value(self, key: str, value):
        if key in self.entries:
            self.entries.move_to_end(key)
        self.entries[key] = value
        if len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
""",
        """from collections import OrderedDict

class RecentItemBuffer:
    def __init__(self, max_items: int):
        self._limit = max_items
        self._store = OrderedDict()

    def _evict_if_needed(self):
        while len(self._store) > self._limit:
            self._store.popitem(last=False)

    def insert(self, item_key: str, payload):
        if item_key in self._store:
            self._store.move_to_end(item_key)
        self._store[item_key] = payload
        self._evict_if_needed()

    def lookup(self, item_key: str):
        if item_key not in self._store:
            return None
        self._store.move_to_end(item_key)
        return self._store[item_key]
""",
    ),
    # 4. Python: TF-IDF cosine scorer (renaming + for->while + helper extraction)
    (
        """import math
from collections import Counter

def compute_tfidf_cosine(doc_one_tokens, doc_two_tokens):
    tf1 = Counter(doc_one_tokens)
    tf2 = Counter(doc_two_tokens)
    vocabulary = set(tf1.keys()) | set(tf2.keys())
    if not vocabulary:
        return 0.0
    dot_prod = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for term in vocabulary:
        df = (1 if term in tf1 else 0) + (1 if term in tf2 else 0)
        idf = math.log((2.0 + 1.0) / (df + 1.0)) + 1.0
        w1 = tf1.get(term, 0) * idf
        w2 = tf2.get(term, 0) * idf
        dot_prod += w1 * w2
        norm_a += w1 * w1
        norm_b += w2 * w2
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_prod / (math.sqrt(norm_a) * math.sqrt(norm_b))
""",
        """import math
from collections import Counter

def _term_idf(present_in_first, present_in_second):
    doc_freq = (1 if present_in_first else 0) + (1 if present_in_second else 0)
    return math.log(3.0 / (doc_freq + 1.0)) + 1.0

def lexical_vector_similarity(words_x, words_y):
    counts_x = Counter(words_x)
    counts_y = Counter(words_y)
    all_terms = list(set(counts_x.keys()).union(set(counts_y.keys())))
    if len(all_terms) == 0:
        return 0.0
    num, den_x, den_y = 0.0, 0.0, 0.0
    idx = 0
    while idx < len(all_terms):
        tok = all_terms[idx]
        weight = _term_idf(tok in counts_x, tok in counts_y)
        vx = counts_x.get(tok, 0) * weight
        vy = counts_y.get(tok, 0) * weight
        num += vx * vy
        den_x += vx * vx
        den_y += vy * vy
        idx += 1
    if den_x == 0.0 or den_y == 0.0:
        return 0.0
    return num / (math.sqrt(den_x) * math.sqrt(den_y))
""",
    ),
    # 5. Java: Binary Search Tree insert & inorder traversal (renaming + method reorder + while)
    (
        """import java.util.ArrayList;
import java.util.List;

public class BinarySearchTree {
    static class Node {
        int key;
        Node left, right;
        Node(int key) { this.key = key; }
    }
    private Node root;

    public void insert(int value) {
        root = insertRec(root, value);
    }

    private Node insertRec(Node current, int value) {
        if (current == null) return new Node(value);
        if (value < current.key) current.left = insertRec(current.left, value);
        else if (value > current.key) current.right = insertRec(current.right, value);
        return current;
    }

    public List<Integer> inorderTraversal() {
        List<Integer> result = new ArrayList<>();
        collectInorder(root, result);
        return result;
    }

    private void collectInorder(Node node, List<Integer> acc) {
        if (node == null) return;
        collectInorder(node.left, acc);
        acc.add(node.key);
        collectInorder(node.right, acc);
    }
}
""",
        """import java.util.ArrayList;
import java.util.List;

public class OrderedIntTree {
    static class TreeNode {
        int val;
        TreeNode lhs, rhs;
        TreeNode(int v) { this.val = v; }
    }
    private TreeNode head;

    public List<Integer> toSortedList() {
        List<Integer> items = new ArrayList<>();
        traverse(head, items);
        return items;
    }

    private void traverse(TreeNode n, List<Integer> out) {
        if (n != null) {
            traverse(n.lhs, out);
            out.add(n.val);
            traverse(n.rhs, out);
        }
    }

    public void addElement(int elem) {
        head = addNode(head, elem);
    }

    private TreeNode addNode(TreeNode cur, int elem) {
        if (cur == null) return new TreeNode(elem);
        if (elem < cur.val) cur.lhs = addNode(cur.lhs, elem);
        else if (elem > cur.val) cur.rhs = addNode(cur.rhs, elem);
        return cur;
    }
}
""",
    ),
    # 6. Java: Matrix Multiplication (for->while + renaming + helper extraction)
    (
        """public class MatrixMultiplier {
    // Multiply two 2D double matrices A (m x k) and B (k x n)
    public static double[][] multiply(double[][] matA, double[][] matB) {
        int rowsA = matA.length;
        int colsA = matA[0].length;
        int colsB = matB[0].length;
        double[][] product = new double[rowsA][colsB];
        for (int i = 0; i < rowsA; i++) {
            for (int j = 0; j < colsB; j++) {
                double sum = 0.0;
                for (int p = 0; p < colsA; p++) {
                    sum += matA[i][p] * matB[p][j];
                }
                product[i][j] = sum;
            }
        }
        return product;
    }
}
""",
        """public class LinearAlgebraOps {
    private static double dotRowCol(double[][] left, double[][] right, int r, int c, int sharedDim) {
        double acc = 0.0;
        int idx = 0;
        while (idx < sharedDim) {
            acc += left[r][idx] * right[idx][c];
            idx++;
        }
        return acc;
    }

    public static double[][] matrixProduct(double[][] left, double[][] right) {
        int m = left.length;
        int k = left[0].length;
        int n = right[0].length;
        double[][] out = new double[m][n];
        int r = 0;
        while (r < m) {
            int c = 0;
            while (c < n) {
                out[r][c] = dotRowCol(left, right, r, c, k);
                c++;
            }
            r++;
        }
        return out;
    }
}
""",
    ),
    # 7. Java: Knapsack 0/1 Dynamic Programming (renaming + for->while + helper)
    (
        """public class KnapsackSolver {
    public static int solveKnapsack(int capacity, int[] weights, int[] values) {
        int n = weights.length;
        int[][] dp = new int[n + 1][capacity + 1];
        for (int i = 1; i <= n; i++) {
            int w = weights[i - 1];
            int v = values[i - 1];
            for (int cap = 0; cap <= capacity; cap++) {
                if (w <= cap) {
                    dp[i][cap] = Math.max(dp[i - 1][cap], dp[i - 1][cap - w] + v);
                } else {
                    dp[i][cap] = dp[i - 1][cap];
                }
            }
        }
        return dp[n][capacity];
    }
}
""",
        """public class OptimalPacker {
    private static int bestChoice(int skipVal, int takeVal) {
        return skipVal >= takeVal ? skipVal : takeVal;
    }

    public static int maxPackedValue(int maxWeight, int[] itemWeights, int[] itemProfits) {
        int count = itemWeights.length;
        int[][] table = new int[count + 1][maxWeight + 1];
        int idx = 1;
        while (idx <= count) {
            int wt = itemWeights[idx - 1];
            int pf = itemProfits[idx - 1];
            int rem = 0;
            while (rem <= maxWeight) {
                int withoutItem = table[idx - 1][rem];
                table[idx][rem] = (wt <= rem)
                    ? bestChoice(withoutItem, table[idx - 1][rem - wt] + pf)
                    : withoutItem;
                rem++;
            }
            idx++;
        }
        return table[count][maxWeight];
    }
}
""",
    ),
    # 8. JavaScript: Debounce & Throttle utilities (function reorder + renaming + comments)
    (
        """// Create a debounced function that delays invocation until waitMs has elapsed
export function createDebounce(callbackFn, waitMs) {
    let timerId = null;
    return function (...args) {
        if (timerId !== null) {
            clearTimeout(timerId);
        }
        timerId = setTimeout(() => {
            timerId = null;
            callbackFn.apply(this, args);
        }, waitMs);
    };
}

export function createThrottle(callbackFn, intervalMs) {
    let lastRun = 0;
    return function (...args) {
        const now = Date.now();
        if (now - lastRun >= intervalMs) {
            lastRun = now;
            callbackFn.apply(this, args);
        }
    };
}
""",
        """export function rateLimitExecution(handler, windowMs) {
    let previousTimestamp = 0;
    return function (...params) {
        const currentTime = Date.now();
        if (currentTime - previousTimestamp >= windowMs) {
            previousTimestamp = currentTime;
            handler.apply(this, params);
        }
    };
}

export function deferExecution(handler, delayMs) {
    let activeHandle = null;
    return function (...params) {
        if (activeHandle !== null) {
            clearTimeout(activeHandle);
        }
        activeHandle = setTimeout(() => {
            activeHandle = null;
            handler.apply(this, params);
        }, delayMs);
    };
}
""",
    ),
    # 9. JavaScript: Breadth-First Graph Shortest Path (for->while + renaming + helper)
    (
        """export function bfsShortestPath(adjacencyList, startNode, targetNode) {
    const queue = [[startNode]];
    const visited = new Set([startNode]);

    while (queue.length > 0) {
        const currentPath = queue.shift();
        const lastVertex = currentPath[currentPath.length - 1];
        if (lastVertex === targetNode) {
            return currentPath;
        }
        const neighbors = adjacencyList[lastVertex] || [];
        for (let i = 0; i < neighbors.length; i++) {
            const nextVertex = neighbors[i];
            if (!visited.has(nextVertex)) {
                visited.add(nextVertex);
                queue.push([...currentPath, nextVertex]);
            }
        }
    }
    return null;
}
""",
        """function expandFrontier(frontierQueue, seenSet, adj, route, node) {
    const adjacent = adj[node] || [];
    let idx = 0;
    while (idx < adjacent.length) {
        const candidate = adjacent[idx];
        if (!seenSet.has(candidate)) {
            seenSet.add(candidate);
            frontierQueue.push(route.concat([candidate]));
        }
        idx++;
    }
}

export function findUnweightedRoute(adj, sourceId, goalId) {
    const frontier = [[sourceId]];
    const seen = new Set([sourceId]);
    while (frontier.length > 0) {
        const route = frontier.shift();
        const tip = route[route.length - 1];
        if (tip === goalId) {
            return route;
        }
        expandFrontier(frontier, seen, adj, route, tip);
    }
    return null;
}
""",
    ),
    # 10. JavaScript: EventEmitter pub/sub class (method reorder + renaming + for->while)
    (
        """export class EventBus {
    constructor() {
        this.listeners = new Map();
    }

    on(eventName, handler) {
        if (!this.listeners.has(eventName)) {
            this.listeners.set(eventName, []);
        }
        this.listeners.get(eventName).push(handler);
    }

    off(eventName, handler) {
        const list = this.listeners.get(eventName);
        if (!list) return;
        this.listeners.set(eventName, list.filter(fn => fn !== handler));
    }

    emit(eventName, payload) {
        const list = this.listeners.get(eventName) || [];
        for (const fn of list) {
            fn(payload);
        }
    }
}
""",
        """export class PubSubChannel {
    constructor() {
        this._registry = new Map();
    }

    publish(topic, data) {
        const subs = this._registry.get(topic) || [];
        let i = 0;
        while (i < subs.length) {
            subs[i](data);
            i++;
        }
    }

    unsubscribe(topic, callback) {
        const subs = this._registry.get(topic);
        if (!subs) return;
        this._registry.set(topic, subs.filter(cb => cb !== callback));
    }

    subscribe(topic, callback) {
        if (!this._registry.has(topic)) {
            this._registry.set(topic, []);
        }
        this._registry.get(topic).push(callback);
    }
}
""",
    ),
]


# --- CODE: 10 Unrelated Pairs (same language per pair, completely different algorithms/domains) ---
CODE_UNRELATED_PAIRS: List[Tuple[str, str]] = [
    # 1. Python: Dijkstra vs CSV Invoice Tax Aggregator
    (
        CODE_PLAGIARIZED_PAIRS[0][0],
        """import csv
from decimal import Decimal

def summarize_regional_invoices(csv_filepath):
    totals_by_region = {}
    with open(csv_filepath, mode='r', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            region = row['region'].strip().upper()
            subtotal = Decimal(row['subtotal'])
            tax_rate = Decimal(row['tax_rate'])
            gross = subtotal * (Decimal('1.0') + tax_rate)
            totals_by_region[region] = totals_by_region.get(region, Decimal('0.00')) + gross
    return {k: str(v.quantize(Decimal('0.01'))) for k, v in totals_by_region.items()}
""",
    ),
    # 2. Python: Merge Sort vs HTTP Retry Token Bucket Client
    (
        CODE_PLAGIARIZED_PAIRS[1][0],
        """import time
import urllib.request
import json

class WebhookDispatcher:
    def __init__(self, endpoint_url: str, auth_token: str):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token

    def post_json_with_backoff(self, payload: dict, max_attempts: int = 3) -> int:
        body = json.dumps(payload).encode('utf-8')
        for attempt in range(max_attempts):
            req = urllib.request.Request(
                self.endpoint_url,
                data=body,
                headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {self.auth_token}'},
                method='POST',
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status
            except Exception:
                time.sleep(2 ** attempt)
        raise RuntimeError('Webhook delivery failed after retries')
""",
    ),
    # 3. Python: LRU Cache vs BMP Image Grayscale Histogram
    (
        CODE_PLAGIARIZED_PAIRS[2][0],
        """def compute_luminance_histogram(rgb_pixels):
    bins = [0] * 256
    for r, g, b in rgb_pixels:
        luminance = int(round(0.299 * r + 0.587 * g + 0.114 * b))
        clamped = max(0, min(255, luminance))
        bins[clamped] += 1
    total = sum(bins) or 1
    return [count / total for count in bins]
""",
    ),
    # 4. Python: TF-IDF Cosine vs SQLite Schema Migration Runner
    (
        CODE_PLAGIARIZED_PAIRS[3][0],
        """import sqlite3

def apply_pending_migrations(db_path: str, migration_sql_map: dict):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS schema_versions (version INT PRIMARY KEY, applied_at TEXT)')
        cur = conn.execute('SELECT version FROM schema_versions')
        applied = {row[0] for row in cur.fetchall()}
        for version in sorted(migration_sql_map.keys()):
            if version not in applied:
                conn.executescript(migration_sql_map[version])
                conn.execute("INSERT INTO schema_versions VALUES (?, datetime('now'))", (version,))
        conn.commit()
    finally:
        conn.close()
""",
    ),
    # 5. Java: BinarySearchTree vs HTTP JWT Header Parser
    (
        CODE_PLAGIARIZED_PAIRS[4][0],
        """import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Optional;

public class BearerHeaderValidator {
    public static Optional<String> extractSubjectClaim(String authorizationHeader) {
        if (authorizationHeader == null || !authorizationHeader.startsWith("Bearer ")) {
            return Optional.empty();
        }
        String token = authorizationHeader.substring(7).trim();
        String[] segments = token.split("\\\\.");
        if (segments.length != 3) {
            return Optional.empty();
        }
        byte[] decoded = Base64.getUrlDecoder().decode(segments[1]);
        String payloadJson = new String(decoded, StandardCharsets.UTF_8);
        return payloadJson.contains("\\"sub\\"") ? Optional.of(payloadJson) : Optional.empty();
    }
}
""",
    ),
    # 6. Java: MatrixMultiplier vs Bank Account Ledger Service
    (
        CODE_PLAGIARIZED_PAIRS[5][0],
        """import java.math.BigDecimal;
import java.util.UUID;

public class SavingsAccountLedger {
    private final UUID accountId;
    private BigDecimal currentBalance;

    public SavingsAccountLedger(UUID accountId, BigDecimal openingBalance) {
        this.accountId = accountId;
        this.currentBalance = openingBalance;
    }

    public synchronized void credit(BigDecimal amount) {
        if (amount.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("Credit must be positive");
        }
        this.currentBalance = this.currentBalance.add(amount);
    }

    public synchronized BigDecimal getCurrentBalance() {
        return this.currentBalance;
    }
}
""",
    ),
    # 7. Java: KnapsackSolver vs INI Configuration File Reader
    (
        CODE_PLAGIARIZED_PAIRS[6][0],
        """import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

public class IniConfigLoader {
    public static Map<String, String> parseKeyValueFile(String filePath) throws IOException {
        Map<String, String> properties = new HashMap<>();
        try (BufferedReader reader = new BufferedReader(new FileReader(filePath))) {
            String line;
            while ((line = reader.readLine()) != null) {
                String trimmed = line.trim();
                if (trimmed.isEmpty() || trimmed.startsWith("#") || !trimmed.contains("=")) continue;
                int sep = trimmed.indexOf('=');
                properties.put(trimmed.substring(0, sep).trim(), trimmed.substring(sep + 1).trim());
            }
        }
        return properties;
    }
}
""",
    ),
    # 8. JavaScript: Debounce/Throttle vs Canvas Particle Physics Renderer
    (
        CODE_PLAGIARIZED_PAIRS[7][0],
        """export function updateParticleSystem(canvasCtx, particles, gravityAccel) {
    canvasCtx.clearRect(0, 0, canvasCtx.canvas.width, canvasCtx.canvas.height);
    for (const p of particles) {
        p.vy += gravityAccel;
        p.x += p.vx;
        p.y += p.vy;
        if (p.y > canvasCtx.canvas.height) {
            p.y = canvasCtx.canvas.height;
            p.vy *= -0.75;
        }
        canvasCtx.beginPath();
        canvasCtx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        canvasCtx.fillStyle = p.color;
        canvasCtx.fill();
    }
}
""",
    ),
    # 9. JavaScript: BFS Shortest Path vs Shopping Cart Coupon Calculator
    (
        CODE_PLAGIARIZED_PAIRS[8][0],
        """export function calculateCheckoutTotal(lineItems, couponCode, shippingFlatRate) {
    let merchandiseSubtotal = 0;
    for (const item of lineItems) {
        merchandiseSubtotal += item.unitPrice * item.quantity;
    }
    let discountAmount = 0;
    if (couponCode === 'WELCOME15' && merchandiseSubtotal >= 50) {
        discountAmount = merchandiseSubtotal * 0.15;
    } else if (couponCode === 'FREESHIP') {
        shippingFlatRate = 0;
    }
    const taxable = Math.max(0, merchandiseSubtotal - discountAmount);
    return Number((taxable * 1.08 + shippingFlatRate).toFixed(2));
}
""",
    ),
    # 10. JavaScript: EventBus vs Cookie String Serializer
    (
        CODE_PLAGIARIZED_PAIRS[9][0],
        """export function serializeHttpCookie(name, value, options = {}) {
    const parts = [`${encodeURIComponent(name)}=${encodeURIComponent(value)}`];
    if (options.maxAge != null) parts.push(`Max-Age=${Math.floor(options.maxAge)}`);
    if (options.domain) parts.push(`Domain=${options.domain}`);
    if (options.path) parts.push(`Path=${options.path}`);
    if (options.secure) parts.push('Secure');
    if (options.httpOnly) parts.push('HttpOnly');
    if (options.sameSite) parts.push(`SameSite=${options.sameSite}`);
    return parts.join('; ');
}
""",
    ),
]


# --- ENGLISH TEXT: 8 Paraphrase Pairs & 8 Unrelated Pairs (each >= 60 words) ---
EN_PARAPHRASE_PAIRS: List[Tuple[str, str]] = [
    (
        "Academic plagiarism detection systems increasingly rely on hybrid architectures that combine lexical fingerprinting with deep semantic representations. While character k-gram methods such as Winnowing excel at locating verbatim copying and minor edits, they struggle when authors thoroughly paraphrase sentences or restructure paragraphs. By integrating dense transformer embeddings, modern evaluation pipelines capture conceptual equivalence across rewritten passages and cross-lingual translations in university submissions.",
        "Modern tools for identifying scholarly misconduct merge surface-level text hashing with neural sentence embeddings inside a unified pipeline. Traditional n-gram techniques like Winnowing reliably catch exact duplication, yet they often miss heavily reworded arguments or reorganized prose. Incorporating contextual vector models enables automated reviewers to recognize shared underlying meaning even when students substantially alter vocabulary and phrasing across academic manuscripts.",
    ),
    (
        "Relational database engines equipped with binary quantization allow organizations to store and search millions of high-dimensional vectors without maintaining a separate external index in memory. Converting floating-point coordinates into compact bit strings reduces storage overhead by more than ninety percent and accelerates candidate retrieval through hardware population-count instructions, after which exact cosine similarity rescoring restores full ranking precision. This design also simplifies backups, access control, and transactional consistency for the stored embeddings.",
        "By applying one-bit quantization inside a standard relational database, engineering teams can query large collections of embedding vectors without operating a dedicated in-memory vector server. Compressing continuous float arrays into binary signatures drastically shrinks disk footprint and speeds up initial filtering via native XOR bit-count operations, while a second pass using full-precision cosine similarity preserves ranking accuracy. Keeping vectors inside the database further eases backup procedures, permission management, and transactional guarantees for embeddings.",
    ),
    (
        "Convolutional neural networks transformed medical image analysis by automatically learning hierarchical visual features directly from raw radiological scans. Early layers respond to simple edges and intensity gradients, whereas deeper layers aggregate these cues into anatomical structures and pathological lesions. Nevertheless, clinical deployment requires rigorous external validation across diverse hospital scanners to prevent domain shift from degrading diagnostic sensitivity. Explainability methods such as saliency maps further help radiologists trust automated predictions.",
        "Deep convolutional architectures revolutionized diagnostic radiology because they extract multi-scale spatial representations straight from unprocessed patient imaging. Initial network stages capture basic boundaries and contrast changes, while subsequent layers assemble those patterns into organs and disease markers. Even so, real-world hospital adoption demands thorough multi-center testing across varied imaging hardware so distribution shifts do not undermine clinical accuracy. Visual explanation tools like heatmaps additionally help clinicians understand and trust the model outputs.",
    ),
    (
        "Distributed consensus protocols such as Raft and Paxos ensure that replicated state machines agree on an ordered sequence of transactions despite network partitions and node crashes. By electing a single leader responsible for appending log entries and requiring a quorum of followers to acknowledge writes before commitment, these algorithms guarantee safety while tolerating minority server failures in cloud infrastructure. Production systems such as etcd rely on this approach.",
        "Fault-tolerant replication frameworks like Paxos and Raft keep cluster nodes synchronized on an identical transaction history even when servers fail or communication links drop. Through leader election and majority quorum acknowledgments prior to committing log updates, such consensus mechanisms maintain strict data consistency across cloud data centers as long as more than half of the replicas remain reachable. Widely deployed stores like etcd and Consul build on these ideas.",
    ),
    (
        "Photovoltaic solar generation introduces significant variability into electrical power grids because irradiance fluctuates rapidly with cloud cover and diurnal cycles. Grid operators mitigate these frequency and voltage disturbances by combining utility-scale lithium-ion battery storage with predictive weather forecasting models, allowing dispatchers to smooth sudden ramps in renewable output and maintain reliable balance between electricity supply and consumer demand. Demand response programs that shift flexible consumption also help absorb surplus midday generation.",
        "Integrating large-scale solar power into transmission networks creates operational challenges since sunlight intensity changes quickly with passing clouds and day-night transitions. To stabilize grid frequency and voltage, utilities pair megawatt battery energy storage systems with short-term meteorological forecasts, enabling control rooms to buffer abrupt swings in photovoltaic production and continuously match generation with load. Flexible demand programs that move consumption to sunny hours likewise help soak up excess daytime solar output.",
    ),
    (
        "Morphological richness in Arabic poses distinct challenges for natural language processing pipelines because clitics, prefixes, and inflectional suffixes attach directly to root words. Effective information retrieval systems therefore normalize orthographic variants such as Alef forms and Teh Marbuta, strip optional diacritical marks, and apply light stemming or subword tokenization before computing lexical overlap or dense semantic embeddings. Without these steps, identical words written with different spellings would be treated as unrelated tokens.",
        "Because Arabic attaches prepositions, conjunctions, and grammatical endings directly onto word stems, its complex morphology complicates automated text analysis. Robust search and similarity engines address this by unifying inconsistent letter shapes including hamza-bearing Alefs, removing short vowel diacritics and tatweel elongation, and segmenting words into subword units prior to indexing documents for lexical or semantic comparison. Skipping such normalization would cause the same word in different spellings to be counted as distinct terms.",
    ),
    (
        "Microservice architectures decompose monolithic enterprise applications into independently deployable services that communicate over lightweight network protocols. Although this separation enables autonomous engineering teams to scale and release components on different schedules, it simultaneously introduces operational complexity around distributed tracing, service discovery, eventual consistency, and cascading timeout failures across inter-service remote procedure calls. Consequently, many organizations adopt service meshes, centralized logging, and standardized deployment pipelines to keep this growing operational burden manageable over time.",
        "Splitting a single large software monolith into fine-grained microservices allows individual development squads to build, scale, and deploy modules on independent timelines. However, communicating across network boundaries brings significant infrastructure overhead, requiring organizations to manage service registries, end-to-end request tracing, asynchronous data synchronization, and circuit breakers that prevent localized latency spikes from cascading system-wide. For this reason, companies frequently introduce service mesh layers, unified log aggregation, and shared release pipelines to control the added operational complexity.",
    ),
    (
        "Randomized controlled trials remain the gold standard for evaluating pharmacological interventions because random allocation balances both observed and unobserved confounding variables across treatment arms. When double-blind masking prevents clinicians and participants from knowing group assignments, researchers can attribute statistically significant differences in clinical outcomes directly to the investigational therapy rather than placebo effects or selection bias. Pre-registration of trial protocols further reduces the risk of selective outcome reporting.",
        "In clinical medicine, randomized trials provide the strongest causal evidence for drug efficacy since assigning patients by chance equalizes known and unknown baseline factors between comparison groups. Combined with double-blinding that conceals treatment identity from both doctors and volunteers, this experimental design ensures that measured improvements reflect true therapeutic activity instead of observer bias or patient expectations. Publishing the study protocol in advance additionally guards against selectively reporting favorable endpoints.",
    ),
]

EN_UNRELATED_PAIRS: List[Tuple[str, str]] = [
    (
        EN_PARAPHRASE_PAIRS[0][0],
        "Plate tectonics governs the long-term geological evolution of continental crust through seafloor spreading at mid-ocean ridges and subduction along convergent margins. As dense oceanic lithosphere sinks into the asthenosphere, partial melting of mantle wedges generates calc-alkaline magma chambers that feed volcanic island arcs and trigger deep-focus seismic activity around the Pacific Ring of Fire. Geologists monitor these regions with dense seismometer networks and satellite measurements of ground deformation.",
    ),
    (
        EN_PARAPHRASE_PAIRS[1][0],
        "Renaissance oil painters in fifteenth-century Flanders perfected translucent glazing techniques by suspending finely ground mineral pigments in drying linseed oil. Applying multiple thin layers over a luminous chalk ground allowed artists such as Jan van Eyck to achieve unprecedented depth of shadow, jewel-like color saturation, and intricate surface reflections on textiles and polished metalware. Conservators today use infrared reflectography to reveal the underdrawings hidden beneath these layered glazes.",
    ),
    (
        EN_PARAPHRASE_PAIRS[2][0],
        "Monetary policy transmission operates through central bank adjustments to overnight interbank interest rates and open-market bond purchases. When inflationary pressures exceed target thresholds, policymakers tighten credit conditions to cool aggregate demand, which raises mortgage borrowing costs, moderates corporate capital expenditure, and gradually stabilizes consumer price indices across the broader macroeconomy. Forward guidance about the future path of interest rates has become an additional tool that shapes market expectations and long-term bond yields.",
    ),
    (
        EN_PARAPHRASE_PAIRS[3][0],
        "Honeybee colonies coordinate nectar foraging across several square kilometers using the waggle dance performed on vertical comb surfaces inside the hive. The angle of the dancer's abdomen relative to gravity encodes the solar azimuth of the floral patch, while the duration of the waggle run communicates flight distance to surrounding worker bees. Karl von Frisch received the Nobel Prize for decoding this remarkable form of symbolic animal communication.",
    ),
    (
        EN_PARAPHRASE_PAIRS[4][0],
        "Classical Roman concrete achieved remarkable durability in marine harbors by mixing volcanic pozzolanic ash from Pozzuoli with lime and seawater. Over centuries of immersion, alkaline fluids reacted with aluminosilicate glass to crystallize rare tobermorite mineral fibers that reinforced microscopic cracks, allowing ancient breakwaters to withstand wave erosion far better than modern Portland cement. Materials scientists now study these ancient recipes to design more sustainable and self-healing marine construction materials.",
    ),
    (
        EN_PARAPHRASE_PAIRS[5][0],
        "Thermohaline circulation drives deep ocean currents across global basins through gradients in water density caused by surface temperature cooling and sea-ice brine rejection. In the North Atlantic, cold saline water masses sink toward the abyssal plain and flow southward, redistributing planetary heat and regulating temperate winter climates across western Europe. Climate scientists warn that melting Greenland ice could freshen surface waters and weaken this overturning circulation during the coming century.",
    ),
    (
        EN_PARAPHRASE_PAIRS[6][0],
        "Crispr-Cas9 genome editing relies on a synthetic single-guide RNA molecule to direct the endonuclease enzyme to a complementary twenty-nucleotide target sequence adjacent to a protospacer motif. Once bound, the protein cleaves both DNA strands, activating cellular repair pathways that either disrupt gene function via non-homologous end joining or insert precise templates. Researchers continue to refine delivery vehicles and high-fidelity enzyme variants to reduce unintended off-target edits in therapeutic applications.",
    ),
    (
        EN_PARAPHRASE_PAIRS[7][0],
        "Gothic cathedral builders in twelfth-century France engineered pointed ribbed vaults and external flying buttresses to transfer outward roof thrusts across slender masonry piers. By relieving load-bearing walls of structural stress, medieval architects opened vast clerestory windows filled with stained glass that illuminated the nave with symbolic colored light. Cathedrals such as Chartres and Notre-Dame de Paris remain celebrated examples of this ambitious structural and artistic achievement across medieval Europe.",
    ),
]


# --- ARABIC TEXT: 8 Paraphrase Pairs & 8 Unrelated Pairs (each >= 60 words) ---
AR_PARAPHRASE_PAIRS: List[Tuple[str, str]] = [
    (
        "تعتمد أنظمة كشف الانتحال العلمي الحديثة في الجامعات العربية على دمج خوارزميات البصمة النصية مع نماذج التعلم العميق للتمثيل الدلالي. فبينما تنجح طرق التجزئة المعجمية في رصد النسخ الحرفي المباشر، فإنها تعجز عن اكتشاف إعادة الصياغة المتقنة واستبدال المفردات بالمرادفات، وهنا تبرز أهمية المتجهات الدلالية التي تقيس تشابه المعاني والأفكار بدقة عالية. كما تتيح هذه الأنظمة للمشرفين الأكاديميين مراجعة المقاطع المتشابهة بصرياً واتخاذ قرارات عادلة ومبنية على أدلة واضحة.",
        "تجمع المنصات المتطورة لفحص الأصالة البحثية في مؤسسات التعليم العالي بين تقنيات مطابقة السلاسل النصية والشبكات العصبية الفهمية. ورغم كفاءة الخوارزميات التقليدية في التقاط الاقتباس النصي المتطابق، إلا أنها تقصر عند قيام الكاتب بتغيير التراكيب اللغوية واستخدام المترادفات، ولذلك تُستخدم نماذج التضمين السياقي لرصد التطابق الفكري والمضموني بين الأبحاث الجامعية. وتمكّن هذه المنصات أعضاء هيئة التدريس من استعراض الفقرات المتطابقة بشكل مرئي وإصدار أحكام منصفة تستند إلى براهين موثقة.",
    ),
    (
        "تواجه معالجة اللغة العربية آلياً تحديات فريدة نتيجة ثرائها الصرفي وتعدد الصيغ الاشتقاقية للكلمة الواحدة واتصال الضمائر وحروف الجر بالجذور. ولمعالجة هذه الخصائص اللغوية، تقوم محركات البحث العلمي بتوحيد أشكال الهمزات والألف والتاء المربوطة وإزالة حركات التشكيل والتطويل قبل تقسيم النصوص إلى وحدات رمزية وحساب درجات التقارب المعجمي والدلالي. ومن دون هذه المعالجة المسبقة تُعامل الكلمة الواحدة المكتوبة بأشكال إملائية مختلفة على أنها كلمات متباينة تماماً مما يضعف دقة المقارنة.",
        "تتسم اللغة العربية ببنية صرفية غنية ومعقدة نظراً لالتصاق اللواصق والسوابق والضمائر بأصول الكلمات وتنوع أوزانها الصرفية، مما يصعّب مهام التحليل الحاسوبي للنصوص. ولتجاوز هذه العقبة، تعمد أنظمة استرجاع المعلومات إلى تطبيع الحروف المتشابهة كالألف والهمزات وحذف علامات التشكيل والمد قبل تجزئة الجمل واستخراج البصمات الرقمية والمتجهات السياقية. وإذا أُهملت خطوة التطبيع هذه فإن اللفظ نفسه بتهجئات متعددة سيُحسب مفردات مستقلة ومتفرقة وهو ما يقلل من جودة نتائج التشابه.",
    ),
    (
        "أسهمت تقنيات الذكاء الاصطناعي والتعلم الآلي في تطوير تشخيص الأمراض المزمنة من خلال تحليل الصور الطبية والسجلات الصحية الإلكترونية بدقة فائقة. وتساعد الشبكات العصبية الالتفافية الأطباء المختصين في الكشف المبكر عن الأورام والتغيرات النسيجية الدقيقة، شريطة التحقق من موثوقية هذه النماذج سريرياً عبر بيانات متنوعة من مستشفيات متعددة. كما تساعد أدوات التفسير المرئي مثل الخرائط الحرارية الأطباء على فهم أسباب قرارات النموذج وزيادة ثقتهم في توصياته التشخيصية اليومية.",
        "أحدثت خوارزميات التعلم العميق والذكاء الاصطناعي نقلة نوعية في المجال الطبي عبر قدرتها على قراءة الأشعة التشخيصية وبيانات المرضى الرقمية بكفاءة عالية. وتدعم هذه النماذج الحاسوبية الكوادر الطبية في رصد المؤشرات المبكرة للأمراض والأورام قبل تفاقمها، مع ضرورة اختبارها ميدانياً في مراكز صحية مختلفة لضمان دقة النتائج وسلامة المرضى. وتُسهم تقنيات الشرح البصري كخرائط الإبراز في توضيح مبررات مخرجات الخوارزمية للأطباء مما يعزز اعتمادهم عليها في الممارسة السريرية المعتادة.",
    ),
    (
        "تُعد الطاقة الشمسية الكهروضوئية من أبرز مصادر الطاقة المتجددة النظيفة التي تسهم في تقليل الانبعاثات الكربونية وحماية البيئة من التلوث الحراري. غير أن تقلب الإشعاع الشمسي بين النهار والليل وتأثره بالغيوم يتطلب ربط محطات التوليد بمنظومات بطاريات تخزين متطورة ونماذج تنبؤ مناخي لضمان استقرار الشبكة الكهربائية وتلبية الطلب المستمر. كما تساعد برامج إدارة الطلب على نقل الاستهلاك المرن إلى ساعات الذروة الشمسية في امتصاص فائض الإنتاج خلال منتصف النهار.",
        "تُمثل منظومات الألواح الشمسية خياراً استراتيجياً لتوليد الكهرباء النظيفة وخفض الغازات الدفيئة المسببة للاحتباس الحراري في الغلاف الجوي. ونظراً لتغير شدة سطوع الشمس تبعاً للظروف الجوية وتعاقب الليل والنهار، تعتمد شركات الكهرباء على وحدات تخزين الطاقة عالية السعة والتوقعات الجوية الدقيقة للحفاظ على توازن التردد واستمرارية الإمداد الكهربائي. وتُسهم خطط ترشيد الأحمال التي تحول جزءاً من الاستهلاك إلى فترات السطوع القوي في استيعاب الكهرباء الزائدة المنتجة وقت الظهيرة.",
    ),
    (
        "تعتمد قواعد البيانات العلائقية الحديثة على تقنيات التكميم الثنائي لضغط المتجهات الرقمية عالية الأبعاد وتخزينها بكفاءة دون الحاجة إلى خوادم فهرسة خارجية مكلفة. ويتيح تحويل القيم العشرية إلى سلاسل بتات ثنائية تقليص حجم الذاكرة المطلوبة بشكل كبير وتسريع عملية الفرز الأولي عبر حساب مسافة هامينغ قبل إعادة الترتيب الدقيق. ويسهل هذا التصميم أيضاً عمليات النسخ الاحتياطي وإدارة صلاحيات الوصول وضمان اتساق المعاملات للمتجهات المخزنة داخل قاعدة البيانات نفسها.",
        "توظف أنظمة إدارة قواعد البيانات المتقدمة أسلوب التحويل الثنائي للمتجهات من أجل حفظ ملايين التضمينات الدلالية داخل الجداول القياسية بأقل استهلاك ممكن للقرص والذاكرة. ومن خلال تمثيل الأرقام العائمة ببتات ثنائية، تتمكن قاعدة البيانات من تصفية المرشحين بسرعة فائقة باستخدام عمليات المقارنة المنطقية ثم حساب تشابه جيب التمام النهائي. كما يؤدي الاحتفاظ بالمتجهات داخل الجداول إلى تبسيط إجراءات الحفظ الاحتياطي والتحكم في الأذونات وتوفير ضمانات المعاملات بصورة موحدة ومتكاملة.",
    ),
    (
        "تتطلب هندسة البرمجيات الموزعة تقسيم الأنظمة الضخمة إلى خدمات مصغرة مستقلة تتواصل فيما بينها عبر واجهات برمجية قياسية وبروتوكولات شبكة خفيفة. ورغم أن هذا التصميم يمنح فرق التطوير مرونة كبيرة في التحديث والتوسع المستقل لكل خدمة، فإنه يفرض تحديات تشغيلية تتعلق بمراقبة الأداء وتتبع الأخطاء وضمان تكامل البيانات. ولذلك تلجأ كثير من المؤسسات إلى شبكات الخدمات وأنظمة السجلات المركزية وخطوط النشر الموحدة للسيطرة على هذا العبء التشغيلي المتزايد.",
        "يقوم نمط المعمارية المعتمدة على الخدمات المصغرة على تفكيك التطبيقات البرمجية المركزية الكبيرة إلى وحدات وظيفية منفصلة تعمل وتترابط عبر الشبكة. وبينما يسهل هذا النهج عمليات النشر المستمر وتوزيع الأحمال بين الخوادم، فإنه يستلزم بناء آليات صارمة لإدارة الاعتماديات المتبادلة ورصد الأعطال الطارئة ومنع تعطل النظام عند تأخر إحدى الخدمات. ولهذا السبب تعتمد الشركات غالباً طبقات وسيطة لإدارة الخدمات وتجميعاً موحداً للسجلات ومسارات إصدار مشتركة لاحتواء التعقيد الإضافي.",
    ),
    (
        "يمثل الأمن السيبراني وحماية البنية التحتية الرقمية أولوية قصوى للمؤسسات المالية والحكومية في ظل تصاعد الهجمات الإلكترونية المتطورة وبرمجيات الفدية الخبيثة. وتشمل استراتيجيات الدفاع الفعالة تطبيق التشفير القوي للبيانات أثناء النقل والتخزين، وتفعيل المصادقة متعددة العوامل، إلى جانب التدريب المستمر للموظفين على اكتشاف رسائل التصيد الاحتيالي. كما يُعد إعداد خطط الاستجابة للحوادث وإجراء اختبارات الاختراق الدورية والنسخ الاحتياطي المنتظم للبيانات من العناصر الأساسية لتقليل الخسائر عند وقوع أي هجوم.",
        "تكتسب منظومات الدفاع السيبراني وأمن المعلومات أهمية بالغة لدى القطاعات المصرفية والهيئات الرسمية لمواجهة التهديدات الرقمية المتزايدة ومحاولات الاختراق. وتقوم خطط الحماية الشاملة على تشفير قواعد البيانات والاتصالات الشبكية، وفرض التحقق الثنائي لهوية المستخدمين، فضلاً عن رفع الوعي الأمني لدى العاملين لتجنب الوقوع في هجمات الهندسة الاجتماعية. ويشكل وضع إجراءات واضحة للتعامل مع الحوادث الأمنية وتنفيذ فحوصات اختراق منتظمة وحفظ نسخ احتياطية دورية ركائز جوهرية للحد من الأضرار عند التعرض لأي اختراق.",
    ),
    (
        "تسهم الإدارة المستدامة للموارد المائية في المناطق الجافة وشبه الجافة في تعزيز الأمن الغذائي والحفاظ على المخزون الجوفي من الاستنزاف الجائر. وتعتمد السياسات الزراعية الرشيدة على استخدام تقنيات الري الحديث بالتنقيط، ومعالجة مياه الصرف لإعادة تدويرها في التشجير، بالإضافة إلى زراعة الأصناف النباتية المقاومة للجفاف والملوحة. كما تسهم حملات التوعية المجتمعية وتسعير المياه بشكل عادل وتشجيع حصاد مياه الأمطار في الحد من الهدر وتحقيق توازن طويل الأمد بين الموارد والاحتياجات.",
        "يُعد ترشيد استهلاك المياه وحوكمة مصادرها الطبيعية ركيزة أساسية لتحقيق التنمية الزراعية المستدامة وحماية الأحواض الجوفية في الأقاليم الشحيحة الأمطار. وتستند الخطط الحديثة في هذا المجال إلى تعميم شبكات الري الذكي عالي الكفاءة، وتنقية المياه المستعملة لاستغلالها مجدداً، مع اختيار المحاصيل الزراعية القادرة على تحمل قلة المياه. وتساعد برامج التثقيف العام ووضع تعرفة منصفة لاستهلاك المياه وتحفيز تجميع مياه السيول والأمطار على تقليل الفاقد وضمان استدامة التوازن بين المتاح والمطلوب.",
    ),
]

AR_UNRELATED_PAIRS: List[Tuple[str, str]] = [
    (
        AR_PARAPHRASE_PAIRS[0][0],
        "تتشكل السلاسل الجبلية البركانية على طول حدود الصفائح التكتونية المتقاربة نتيجة غوص القشرة المحيطية الكثيفة تحت القشرة القارية في طبقة الوشاح الأرضي. ومع ارتفاع درجات الحرارة والضغط في الأعماق السحيقة، تنصهر الصخور جزئياً لتكون غرفاً صهارية تندفع نحو السطح مسببة ثورانات بركانية وزلازل تكتونية عميقة البؤرة. ويرصد علماء الجيولوجيا هذه المناطق النشطة باستخدام شبكات كثيفة من أجهزة قياس الزلازل وصور الأقمار الصناعية لقياس تشوهات سطح الأرض بدقة وتوقع الثورانات المحتملة.",
    ),
    (
        AR_PARAPHRASE_PAIRS[1][0],
        "تتميز العمارة الإسلامية التاريخية في الأندلس والمغرب ببراعة توظيف الزخارف الهندسية المتناظرة والفسيفساء الخزفية الملونة إلى جانب الأقواس الحدوية والمقرنصات الجصية الدقيقة. وقد صممت الأفنية الداخلية المفتوحة المزودة بالنوافير المائية وقنوات السلسبيل لتلطيف درجات الحرارة وتوفير بيئة هادئة تجمع بين الجمال البصري والوظيفة المناخية. ولا تزال قصور الحمراء في غرناطة وجامع القرويين في فاس شاهدة حتى اليوم على عبقرية الحرفيين والمهندسين في تلك الحقبة الحضارية المزدهرة من التاريخ.",
    ),
    (
        AR_PARAPHRASE_PAIRS[2][0],
        "تعتمد السياسة النقدية في البنوك المركزية على التحكم في أسعار الفائدة الأساسية ونسب الاحتياطي الإلزامي للبنوك التجارية بهدف كبح التضخم المالي والحفاظ على استقرار القوة الشرائية للعملة الوطنية. وعندما ترتفع معدلات الأسعار الاستهلاكية، تتجه السلطات النقدية إلى تقليص المعروض النقدي وتشديد شروط الائتمان والتمويل الاستثماري. كما أصبحت التوجيهات المستقبلية الصادرة عن صناع القرار بشأن مسار أسعار الفائدة أداة إضافية مؤثرة في توقعات الأسواق المالية وعوائد السندات الحكومية طويلة الأجل.",
    ),
    (
        AR_PARAPHRASE_PAIRS[3][0],
        "تهاجر أسراب الطيور المائية آلاف الكيلومترات سنوياً بين مناطق التكاثر الشمالية والمناطق الدافئة جنوباً مسترشدة بالمجال المغناطيسي للأرض ومواقع الشمس والنجوم والتضاريس الجغرافية الساحلية. وتعتمد هذه الطيور على الأراضي الرطبة والبحيرات الطبيعية كمحطات استراحة حيوية للتزود بالغذاء وتخزين الدهون اللازمة لمواصلة رحلاتها الطويلة عبر القارات. ويهدد تجفيف المستنقعات والتوسع العمراني والتغير المناخي هذه المحطات الطبيعية الحيوية مما يدفع منظمات البيئة الدولية إلى إنشاء محميات خاصة لحماية مسارات الهجرة التقليدية.",
    ),
    (
        AR_PARAPHRASE_PAIRS[4][0],
        "تقوم عملية التمثيل الضوئي في النباتات الخضراء على امتصاص الطاقة الضوئية بواسطة صبغة الكلوروفيل الموجودة داخل البلاستيدات الخضراء في خلايا الأوراق. وتُستخدم هذه الطاقة لتحويل غاز ثاني أكسيد الكربون الجوي والماء الممتص من التربة إلى مركبات الجلوكوز العضوية اللازمة لنمو النبات مع إطلاق غاز الأكسجين النقي. وتتأثر كفاءة هذه العملية الحيوية بشدة الإضاءة ودرجة الحرارة وتركيز ثاني أكسيد الكربون في الهواء وتوافر العناصر المعدنية الضرورية كالمغنيسيوم والنيتروجين في التربة.",
    ),
    (
        AR_PARAPHRASE_PAIRS[5][0],
        "ازدهرت التجارة البحرية القديمة في المحيط الهندي والبحر الأحمر بفضل اكتشاف البحارة العرب لنظام الرياح الموسمية المنتظمة بين الصيف والشتاء. وقد مكنت السفن الشراعية الخشبية المتينة من نقل البخور والتوابل والحرير والأخشاب الثمينة بين موانئ اليمن وعمان وسواحل شرق أفريقيا والهند وجنوب شرق آسيا. وقد أسهمت هذه الشبكة التجارية الواسعة في تبادل المعارف والثقافات واللغات بين الشعوب ونشأة مدن ساحلية مزدهرة أصبحت مراكز حضارية واقتصادية مؤثرة لعدة قرون متتالية.",
    ),
    (
        AR_PARAPHRASE_PAIRS[6][0],
        "تتكون النجوم العملاقة داخل السدم الغازية الكثيفة عندما تنهار سحب الهيدروجين والهيليوم تحت تأثير جاذبيتها الذاتية فترتفع حرارة المركز إلى ملايين الدرجات. وعند بدء تفاعلات الاندماج النووي الهيدروجيني، يتولد ضغط إشعاعي هائل يوازن قوة الجاذبية ويحافظ على استقرار النجم وتوهجه لملايين أو مليارات السنين. وعندما ينفد وقود الهيدروجين في قلب النجم الضخم يتمدد ليصبح عملاقاً أحمر ثم ينفجر في نهاية حياته على هيئة مستعر أعظم يقذف العناصر الثقيلة إلى الفضاء الكوني الواسع.",
    ),
    (
        AR_PARAPHRASE_PAIRS[7][0],
        "تُصنع الآلات الموسيقية الوترية التقليدية كالعود والكمان من أخشاب مختارة بعناية مثل خشب الجوز والأرز والقيقب بعد تجفيفها طبيعياً لسنوات طويلة. ويؤثر سمك الصندوق الصوتي وانحناء الأضلاع الخشبية ونوعية الأوتار المشدودة بشكل مباشر على نقاء الرنين الصوتي وعمق النغمات الموسيقية الصادرة عند العزف. ويتوارث الحرفيون المهرة أسرار هذه الصناعة الدقيقة جيلاً بعد جيل في ورش صغيرة بمدن مثل دمشق والقاهرة وبغداد حيث تُصقل كل قطعة يدوياً بعناية فائقة وصبر طويل.",
    ),
]


def _verify_dataset_integrity() -> None:
    assert len(CODE_PLAGIARIZED_PAIRS) >= 10
    assert len(CODE_UNRELATED_PAIRS) >= 10
    assert len(EN_PARAPHRASE_PAIRS) >= 8
    assert len(EN_UNRELATED_PAIRS) >= 8
    assert len(AR_PARAPHRASE_PAIRS) >= 8
    assert len(AR_UNRELATED_PAIRS) >= 8

    for idx, (a, b) in enumerate(EN_PARAPHRASE_PAIRS + EN_UNRELATED_PAIRS):
        assert len(a.split()) >= 60, f"EN pair {idx} side A has < 60 words ({len(a.split())})"
        assert len(b.split()) >= 60, f"EN pair {idx} side B has < 60 words ({len(b.split())})"

    for idx, (a, b) in enumerate(AR_PARAPHRASE_PAIRS + AR_UNRELATED_PAIRS):
        assert len(a.split()) >= 60, f"AR pair {idx} side A has < 60 words ({len(a.split())})"
        assert len(b.split()) >= 60, f"AR pair {idx} side B has < 60 words ({len(b.split())})"


def compute_pairwise_auc(pos_scores: List[float], neg_scores: List[float]) -> float:
    """Compute exact Mann-Whitney / ROC AUC by pairwise ranking without sklearn."""
    total = len(pos_scores) * len(neg_scores)
    if total == 0:
        return 0.0
    wins = 0.0
    for p in pos_scores:
        for u in neg_scores:
            if p > u:
                wins += 1.0
            elif p == u:
                wins += 0.5
    return wins / total


def evaluate_pairs(
    model: SentenceTransformer,
    pos_pairs: List[Tuple[str, str]],
    neg_pairs: List[Tuple[str, str]],
) -> Dict[str, float]:
    all_texts: List[str] = []
    for a, b in pos_pairs:
        all_texts.append(a[:4000])
        all_texts.append(b[:4000])
    for a, b in neg_pairs:
        all_texts.append(a[:4000])
        all_texts.append(b[:4000])

    embs = model.encode(all_texts, convert_to_numpy=True, normalize_embeddings=True, batch_size=32)
    embs = np.asarray(embs, dtype="float32")

    pos_scores: List[float] = []
    idx = 0
    for _ in pos_pairs:
        sim = float(np.dot(embs[idx], embs[idx + 1]))
        pos_scores.append(sim)
        idx += 2

    neg_scores: List[float] = []
    for _ in neg_pairs:
        sim = float(np.dot(embs[idx], embs[idx + 1]))
        neg_scores.append(sim)
        idx += 2

    pos_mean = float(np.mean(pos_scores))
    pos_min = float(np.min(pos_scores))
    pos_max = float(np.max(pos_scores))
    neg_mean = float(np.mean(neg_scores))
    neg_min = float(np.min(neg_scores))
    neg_max = float(np.max(neg_scores))
    margin = pos_min - neg_max
    auc = compute_pairwise_auc(pos_scores, neg_scores)

    return {
        "pos_mean": round(pos_mean, 4),
        "pos_min": round(pos_min, 4),
        "pos_max": round(pos_max, 4),
        "neg_mean": round(neg_mean, 4),
        "neg_min": round(neg_min, 4),
        "neg_max": round(neg_max, 4),
        "margin": round(margin, 4),
        "auc": round(auc, 4),
        "floor": round(neg_mean, 2),
    }


def main() -> None:
    _verify_dataset_integrity()

    models_dir = Path(os.environ.get("MODELS_DIR", r"D:\AI engine\models"))
    if not models_dir.exists():
        models_dir = Path(r"D:\AI engine\models")

    code_candidates = ["codebert-base", "unixcoder-base"]
    text_candidates = ["bge-m3", "multilingual-e5-base", "LaBSE"]

    results_code: Dict[str, Dict[str, float]] = {}
    for m_name in code_candidates:
        m_path = models_dir / m_name
        print(f"[Calibration] Evaluating code model: {m_name} ...")
        model = SentenceTransformer(str(m_path))
        results_code[m_name] = evaluate_pairs(model, CODE_PLAGIARIZED_PAIRS, CODE_UNRELATED_PAIRS)

    results_en: Dict[str, Dict[str, float]] = {}
    results_ar: Dict[str, Dict[str, float]] = {}
    for m_name in text_candidates:
        m_path = models_dir / m_name
        print(f"[Calibration] Evaluating text model (EN + AR): {m_name} ...")
        model = SentenceTransformer(str(m_path))
        results_en[m_name] = evaluate_pairs(model, EN_PARAPHRASE_PAIRS, EN_UNRELATED_PAIRS)
        results_ar[m_name] = evaluate_pairs(model, AR_PARAPHRASE_PAIRS, AR_UNRELATED_PAIRS)

    # Apply Decision Rule for Code: higher AUC; tie-breaker: larger margin
    chosen_code_model = sorted(
        code_candidates,
        key=lambda m: (results_code[m]["auc"], results_code[m]["margin"]),
        reverse=True,
    )[0]

    # Apply Decision Rule for Text: keep bge-m3 unless another beats it by >= 0.05 AUC on BOTH EN and AR
    chosen_text_model = "bge-m3"
    bge_en_auc = results_en["bge-m3"]["auc"]
    bge_ar_auc = results_ar["bge-m3"]["auc"]
    for cand in text_candidates:
        if cand == "bge-m3":
            continue
        if (results_en[cand]["auc"] - bge_en_auc >= 0.05) and (results_ar[cand]["auc"] - bge_ar_auc >= 0.05):
            chosen_text_model = cand
            break

    # Compute recommended SEMANTIC_CALIBRATION_FLOOR per model
    # For text models, average the EN and AR unrelated means and round to 2 decimals
    floors: Dict[str, float] = {}
    for m_name in code_candidates:
        floors[m_name] = results_code[m_name]["floor"]
    for m_name in text_candidates:
        avg_neg = 0.5 * (results_en[m_name]["neg_mean"] + results_ar[m_name]["neg_mean"])
        floors[m_name] = round(avg_neg, 2)

    lines = [
        "# Semantic Embedding Model Calibration & Discrimination Report",
        "",
        "Generated by `scripts/calibrate_semantic_models.py` on in-code labeled pairs",
        "(10 plagiarized + 10 unrelated code pairs across Python/Java/JS; 8 paraphrase + 8 unrelated",
        "English academic pairs >= 60 words; 8 paraphrase + 8 unrelated Modern Standard Arabic pairs >= 60 words).",
        "",
        "## 1. Code Domain (`Python`, `Java`, `JavaScript`)",
        "",
        "| Model | Plagiarized Mean (Min / Max) | Unrelated Mean (Min / Max) | Margin (`min_pos - max_neg`) | ROC-AUC | Recommended Floor |",
        "|---|---|---|---|---|---|",
    ]
    for m_name in code_candidates:
        r = results_code[m_name]
        lines.append(
            f"| `{m_name}` | {r['pos_mean']:.4f} ({r['pos_min']:.4f} / {r['pos_max']:.4f}) "
            f"| {r['neg_mean']:.4f} ({r['neg_min']:.4f} / {r['neg_max']:.4f}) "
            f"| {r['margin']:+.4f} | **{r['auc']:.4f}** | `{r['floor']:.2f}` |"
        )

    lines.extend([
        "",
        "## 2. English Academic Text Domain (>= 60 words per document)",
        "",
        "| Model | Paraphrase Mean (Min / Max) | Unrelated Mean (Min / Max) | Margin (`min_pos - max_neg`) | ROC-AUC | Unrelated Floor (EN) |",
        "|---|---|---|---|---|---|",
    ])
    for m_name in text_candidates:
        r = results_en[m_name]
        lines.append(
            f"| `{m_name}` | {r['pos_mean']:.4f} ({r['pos_min']:.4f} / {r['pos_max']:.4f}) "
            f"| {r['neg_mean']:.4f} ({r['neg_min']:.4f} / {r['neg_max']:.4f}) "
            f"| {r['margin']:+.4f} | **{r['auc']:.4f}** | `{r['floor']:.2f}` |"
        )

    lines.extend([
        "",
        "## 3. Modern Standard Arabic Text Domain (>= 60 words per document)",
        "",
        "| Model | Paraphrase Mean (Min / Max) | Unrelated Mean (Min / Max) | Margin (`min_pos - max_neg`) | ROC-AUC | Unrelated Floor (AR) |",
        "|---|---|---|---|---|---|",
    ])
    for m_name in text_candidates:
        r = results_ar[m_name]
        lines.append(
            f"| `{m_name}` | {r['pos_mean']:.4f} ({r['pos_min']:.4f} / {r['pos_max']:.4f}) "
            f"| {r['neg_mean']:.4f} ({r['neg_min']:.4f} / {r['neg_max']:.4f}) "
            f"| {r['margin']:+.4f} | **{r['auc']:.4f}** | `{r['floor']:.2f}` |"
        )

    lines.extend([
        "",
        "## 4. Selected Models & Calibration Floors",
        "",
        f"- **Selected Code Model:** `{chosen_code_model}` (AUC = {results_code[chosen_code_model]['auc']:.4f}, Margin = {results_code[chosen_code_model]['margin']:+.4f})",
        f"- **Selected Text Model:** `{chosen_text_model}` (EN AUC = {results_en[chosen_text_model]['auc']:.4f}, AR AUC = {results_ar[chosen_text_model]['auc']:.4f})",
        "",
        "### `SEMANTIC_CALIBRATION_FLOOR` (written to `plagiarism_engine/config.py`)",
        "```python",
        "SEMANTIC_CALIBRATION_FLOOR = {",
    ])
    for k, v in floors.items():
        lines.append(f'    "{k}": {v:.2f},')
    lines.extend([
        "}",
        "```",
        "",
    ])

    report_path = PROJECT_ROOT / "calibration_results.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"[Calibration] Wrote report to {report_path}")


if __name__ == "__main__":
    main()
