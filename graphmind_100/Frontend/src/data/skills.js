export const skills = [
  // 🧠 Core Thinking Layer (Frontal Cortex)
  {
    id: "recursion",
    label: "Recursion",
    mastery: 0.4,
    centrality: 1.0,
    priority: 0.9,
    position: [-2, 2, 0],
    dependencies: []
  },
  {
    id: "backtracking",
    label: "Backtracking",
    mastery: 0.3,
    centrality: 0.9,
    priority: 0.8,
    position: [-1, 1, 1],
    dependencies: ["recursion"]
  },
  {
    id: "dp",
    label: "Dynamic Programming",
    mastery: 0.3,
    centrality: 1.2,
    priority: 1.0,
    position: [0, 2, 0],
    dependencies: ["recursion"]
  },

  // 🔗 Structural Layer (Parietal Cortex)
  {
    id: "arrays",
    label: "Arrays",
    mastery: 0.8,
    centrality: 0.8,
    priority: 0.7,
    position: [-3, 0, 0],
    dependencies: []
  },
  {
    id: "linkedlist",
    label: "Linked List",
    mastery: 0.6,
    centrality: 0.8,
    priority: 0.6,
    position: [-2, -1, 1],
    dependencies: ["arrays"]
  },
  {
    id: "stack",
    label: "Stack",
    mastery: 0.7,
    centrality: 0.7,
    priority: 0.6,
    position: [-1, -2, 0],
    dependencies: ["arrays"]
  },
  {
    id: "queue",
    label: "Queue",
    mastery: 0.6,
    centrality: 0.7,
    priority: 0.6,
    position: [1, -2, 0],
    dependencies: ["arrays"]
  },

  // 🌳 Tree / Graph Intelligence (Temporal Cortex)
  {
    id: "trees",
    label: "Trees",
    mastery: 0.5,
    centrality: 1.0,
    priority: 0.9,
    position: [2, 1, 0],
    dependencies: ["recursion"]
  },
  {
    id: "bst",
    label: "Binary Search Tree",
    mastery: 0.4,
    centrality: 0.9,
    priority: 0.7,
    position: [3, 2, 1],
    dependencies: ["trees"]
  },
  {
    id: "heaps",
    label: "Heap / Priority Queue",
    mastery: 0.3,
    centrality: 0.9,
    priority: 0.8,
    position: [2, -1, 1],
    dependencies: ["trees"]
  },
  {
    id: "graphs",
    label: "Graphs",
    mastery: 0.6,
    centrality: 1.3,
    priority: 1.0,
    position: [3, 0, 0],
    dependencies: ["trees"]
  },

  // ⚡ Optimization Cortex
  {
    id: "greedy",
    label: "Greedy Algorithms",
    mastery: 0.85,
    centrality: 0.9,
    priority: 0.8,
    position: [1, 1, -1],
    dependencies: ["arrays"]
  },
  {
    id: "binarysearch",
    label: "Binary Search",
    mastery: 0.7,
    centrality: 0.8,
    priority: 0.7,
    position: [0, 0, -2],
    dependencies: ["arrays"]
  },

  // 🧬 Advanced Brain Connections
  {
    id: "trie",
    label: "Trie",
    mastery: 0.2,
    centrality: 0.7,
    priority: 0.6,
    position: [4, 1, 1],
    dependencies: ["trees"]
  },
  {
    id: "segmenttree",
    label: "Segment Tree",
    mastery: 0.1,
    centrality: 1.0,
    priority: 0.9,
    position: [1, 3, 1],
    dependencies: ["trees", "arrays"]
  }
];
