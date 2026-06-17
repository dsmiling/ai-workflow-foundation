# AI 增强解析提示包

你是仓库理解助手。请基于下面的本地证据包输出高密度、可回填到 github_repo_localizer 的 JSON 结果。

要求：
- 只根据给定证据推断，不要编造未出现的文件、模块或命令。
- 所有面向用户展示的结论、摘要、用途、场景、风险、建议都必须使用自然中文表达。
- 如果证据里的 README、注释、字段说明或配置项是英文，请先翻译成中文再写入输出；必要时可在中文后用括号保留原始英文术语。
- 不要把整段英文原文直接塞进 仓库用途、适用场景、项目价值评估 等展示字段。
- 明确区分：结构层、核心能力层、支撑层。
- 优先回答：项目用途、使用判断、技术架构、核心能力模块、关键链路、接入建议、风险。
- 输出必须是合法 JSON。
- 如果证据不足，请在 uncertainty_notes 中说明。
- 如果证据包里包含 deep_dive_notes，请把这些后续追问与确认结果视为高优先级补充上下文，用来修正和细化之前的项目解构。

## 目标 JSON Schema

```json
{
  "mode": "ai-analysis-v1",
  "project_positioning": {
    "repository_type": "string",
    "repository_purpose": "string",
    "target_users": [
      "string"
    ],
    "suitable_scenarios": [
      "string"
    ]
  },
  "architecture": {
    "architecture_style": "string",
    "runtime_boundaries": [
      "string"
    ],
    "technical_highlights": [
      "string"
    ]
  },
  "critical_flows": [
    "string"
  ],
  "core_modules": [
    {
      "module_name": "string",
      "role": "string",
      "responsibility": "string",
      "key_files": [
        "string"
      ],
      "dependencies": [
        "string"
      ],
      "is_core": true
    }
  ],
  "supporting_modules": [
    {
      "module_name": "string",
      "role": "string",
      "responsibility": "string",
      "key_files": [
        "string"
      ]
    }
  ],
  "integration_judgement": {
    "direct_use_judgement": "string",
    "workflow_fit": "string",
    "integration_advice": [
      "string"
    ]
  },
  "project_value_assessment": {
    "project_class": "独立项目|问题解决方案|工具链插件|能力模块|示例/实验项目",
    "project_scale": "高|中|低",
    "impact_scope": "string",
    "problems_solved": [
      "string"
    ],
    "solution_comparison": [
      "string"
    ],
    "integration_cost": "高|中|低",
    "suitable_project_types": [
      "string"
    ],
    "plug_and_play_readiness": "可直接试用|可局部接入|更适合参考实现|不建议直接接入",
    "evidence_strength": "高|中|低",
    "roi_assessment": {
      "roi_level": "高|中|低",
      "expected_benefits": [
        "string"
      ],
      "expected_costs": [
        "string"
      ],
      "payback_period": "短期|中期|长期"
    },
    "decision_summary": {
      "recommended_action": "建议直接试用|建议局部抽取|建议作为参考实现|建议暂不投入",
      "why": [
        "string"
      ],
      "expected_return": "string",
      "main_constraints": [
        "string"
      ]
    },
    "value_scorecard": {
      "problem_value": {
        "label": "问题价值",
        "level": "高|中|低",
        "summary": "string"
      },
      "technical_distinctiveness": {
        "label": "技术亮点",
        "level": "高|中|低",
        "summary": "string"
      },
      "integration_feasibility": {
        "label": "接入可行性",
        "level": "高|中|低",
        "summary": "string"
      },
      "adoption_advice": {
        "label": "采用建议",
        "level": "高|中|低",
        "summary": "string"
      }
    },
    "evaluation_dimensions": {
      "project_framing": {
        "label": "项目归属与定位",
        "conclusion": "string",
        "reasoning": [
          "string"
        ],
        "evidence": [
          "string"
        ],
        "risks": [
          "string"
        ],
        "recommended_actions": [
          "string"
        ]
      },
      "problem_value": {
        "label": "问题价值",
        "conclusion": "string",
        "reasoning": [
          "string"
        ],
        "evidence": [
          "string"
        ],
        "risks": [
          "string"
        ],
        "recommended_actions": [
          "string"
        ]
      },
      "technical_maturity": {
        "label": "技术完成度",
        "conclusion": "string",
        "reasoning": [
          "string"
        ],
        "evidence": [
          "string"
        ],
        "risks": [
          "string"
        ],
        "recommended_actions": [
          "string"
        ]
      },
      "integration_feasibility": {
        "label": "接入可行性",
        "conclusion": "string",
        "reasoning": [
          "string"
        ],
        "evidence": [
          "string"
        ],
        "risks": [
          "string"
        ],
        "recommended_actions": [
          "string"
        ]
      },
      "differentiation": {
        "label": "替代性与差异化",
        "conclusion": "string",
        "reasoning": [
          "string"
        ],
        "evidence": [
          "string"
        ],
        "risks": [
          "string"
        ],
        "recommended_actions": [
          "string"
        ]
      },
      "adoption_decision": {
        "label": "投入建议",
        "conclusion": "string",
        "reasoning": [
          "string"
        ],
        "evidence": [
          "string"
        ],
        "risks": [
          "string"
        ],
        "recommended_actions": [
          "string"
        ]
      }
    }
  },
  "risks": [
    {
      "summary": "string",
      "severity": "high|medium|low",
      "evidence": [
        "string"
      ]
    }
  ],
  "evidence_links": [
    {
      "topic": "string",
      "paths": [
        "string"
      ]
    }
  ],
  "uncertainty_notes": [
    "string"
  ],
  "fast_analysis": {
    "mode": "fast-analysis",
    "project": {}
  },
  "explainable_analysis": {
    "mode": "explainable-analysis"
  }
}
```

## 本地证据包

```json
{
  "mode": "llm-context-v1",
  "repository": {
    "name": "ai-workflow-foundation",
    "root_path": "G:\\FF_Wang\\ProjectStudy\\ai-workflow-foundation\\ai-workflow-foundation",
    "source_url": "local://G:/FF_Wang/ProjectStudy/ai-workflow-foundation/ai-workflow-foundation",
    "source": "local",
    "owner": "local",
    "repo": "ai-workflow-foundation"
  },
  "project_summary": {
    "summary": "AI Workflow Foundation is a local-first foundation for personal AI workflows。整体属于 Python 应用或服务工程。",
    "purpose": [
      "核心特性：Workflow definitions are files.。",
      "核心特性：Nodes have explicit inputs, outputs, skills, and approval modes.。",
      "核心特性：Artifacts are written to disk.。",
      "核心特性：Runs can pause for review.。",
      "仓库当前暴露出 6 个主要顶层模块，说明它不是单一脚本，而是具备明确分层的工程项目。"
    ],
    "architecture_style": "Python 应用或服务工程",
    "runtime_boundaries": [
      "desktop：承担该层的主要代码与资源组织职责，主要技术为 JSON。",
      "docs：保存项目说明、设计文档和使用指南。，主要技术为 Markdown。",
      "examples：展示项目的用法、演示或样例工程。，主要技术为 JSON、Markdown。",
      "src：承载前端入口、页面编排与交互逻辑。，主要技术为 Python。",
      "tests：汇总测试代码、夹具和验证逻辑。，主要技术为 Python。",
      "web：提供浏览器侧界面、状态和交互能力。，主要技术为 待进一步识别。"
    ],
    "technical_highlights": [
      "主要语言：Python、Rust。",
      "框架线索：Rust crate 布局。",
      "构建与工具链：cargo。",
      "质量保障线索：Repository contains visible test/spec-related files。",
      "关键清单文件：desktop\\package-lock.json、desktop\\package.json、desktop\\src-tauri\\Cargo.toml、pyproject.toml。",
      "已识别入口文件：desktop\\node_modules\\@tauri-apps\\cli\\index.js、desktop\\node_modules\\@tauri-apps\\cli\\main.js。"
    ],
    "key_execution_paths": [
      "当前关键链路仍以顶层模块协作为主，建议继续结合源码调用图做下一层细化。"
    ]
  },
  "inventory": {
    "top_level_dirs": [
      ".aiwf",
      ".doctor-workspace",
      ".repo_reports",
      ".test-debug",
      ".test-tmp",
      ".test-workspace",
      "desktop",
      "docs",
      "examples",
      "src",
      "tests",
      "web"
    ],
    "top_level_files": [
      ".gitignore",
      "aiwf_cli.py",
      "Launch-AIWF.ps1",
      "pyproject.toml",
      "README.md"
    ],
    "manifest_files": [
      "desktop\\package-lock.json",
      "desktop\\package.json",
      "desktop\\src-tauri\\Cargo.toml",
      "pyproject.toml"
    ],
    "doc_files": [
      ".aiwf\\runs\\run_20260610-134037-856535\\artifacts\\build_plan.md",
      ".aiwf\\runs\\run_20260610-134037-856535\\artifacts\\module_breakdown.md",
      ".aiwf\\runs\\run_20260610-134037-856535\\artifacts\\requirement_analysis.md",
      ".aiwf\\runs\\run_20260610-134037-856535\\revisions\\rev_20260610-134112-090878\\artifacts\\build_plan.md",
      ".aiwf\\runs\\run_20260610-134037-856535\\revisions\\rev_20260610-134112-090878\\artifacts\\module_breakdown.md",
      ".aiwf\\runs\\run_20260610-134037-856535\\revisions\\rev_20260610-134112-090878\\artifacts\\requirement_analysis.md",
      ".aiwf\\runs\\run_20260610-135500-549457\\artifacts\\build_plan.md",
      ".aiwf\\runs\\run_20260610-135500-549457\\artifacts\\module_breakdown.md",
      ".aiwf\\runs\\run_20260610-135500-549457\\artifacts\\requirement_analysis.md",
      ".aiwf\\runs\\run_20260610-140006-822624\\artifacts\\module_breakdown.md",
      ".aiwf\\runs\\run_20260610-140006-822624\\artifacts\\requirement_analysis.md",
      ".aiwf\\runs\\run_20260610-140148-455914\\artifacts\\module_breakdown.md",
      ".aiwf\\runs\\run_20260610-140148-455914\\artifacts\\requirement_analysis.md",
      ".aiwf\\runs\\run_20260610-142618-210854\\artifacts\\module_breakdown.md",
      ".aiwf\\runs\\run_20260610-142618-210854\\artifacts\\requirement_analysis.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\artifacts\\build_plan.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\artifacts\\module_breakdown.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\artifacts\\requirement_analysis.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\revisions\\rev_20260610-144134-112702\\artifacts\\build_plan.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\revisions\\rev_20260610-144134-112702\\artifacts\\module_breakdown.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\revisions\\rev_20260610-144134-112702\\artifacts\\requirement_analysis.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\revisions\\rev_20260610-144134-130878\\artifacts\\build_plan.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\revisions\\rev_20260610-144134-130878\\artifacts\\module_breakdown.md",
      ".doctor-workspace\\.aiwf\\runs\\run_20260610-144134-077091\\revisions\\rev_20260610-144134-130878\\artifacts\\requirement_analysis.md"
    ],
    "ci_files": [],
    "container_files": [],
    "total_files": 8192
  },
  "signals": {
    "languages": [
      "Python",
      "Rust"
    ],
    "frameworks": [
      "Rust crate 布局"
    ],
    "package_managers": [
      "npm",
      "pyproject-based Python packaging",
      "cargo"
    ],
    "build_tools": [
      "cargo"
    ],
    "quality_tools": [
      "Repository contains visible test/spec-related files"
    ],
    "runtime_targets": [
      "Node.js",
      "Python",
      "Rust"
    ]
  },
  "candidate_modules": [
    {
      "name": "desktop",
      "path": "desktop",
      "category": "目录模块",
      "responsibility": "作为 `desktop` 路径下的主模块，承载该层的主要代码与资源。",
      "technologies": [
        "JSON"
      ],
      "key_files": [
        "desktop\\node_modules\\@tauri-apps\\cli\\index.js",
        "desktop\\node_modules\\@tauri-apps\\cli\\main.js",
        "desktop\\node_modules\\@tauri-apps\\cli-win32-x64-msvc\\package.json",
        "desktop\\node_modules\\@tauri-apps\\cli\\package.json",
        "desktop\\package.json",
        "desktop\\src-tauri\\Cargo.toml"
      ],
      "relation_targets": [],
      "child_modules": []
    },
    {
      "name": "docs",
      "path": "docs",
      "category": "文档中心",
      "responsibility": "保存项目说明、设计文档和使用指南。",
      "technologies": [
        "Markdown"
      ],
      "key_files": [],
      "relation_targets": [],
      "child_modules": []
    },
    {
      "name": "examples",
      "path": "examples",
      "category": "示例集合",
      "responsibility": "展示项目的用法、演示或样例工程。",
      "technologies": [
        "JSON",
        "Markdown"
      ],
      "key_files": [],
      "relation_targets": [],
      "child_modules": []
    },
    {
      "name": "src",
      "path": "src",
      "category": "前端源码",
      "responsibility": "承载前端入口、页面编排与交互逻辑。",
      "technologies": [
        "Python"
      ],
      "key_files": [],
      "relation_targets": [],
      "child_modules": []
    },
    {
      "name": "tests",
      "path": "tests",
      "category": "测试集合",
      "responsibility": "汇总测试代码、夹具和验证逻辑。",
      "technologies": [
        "Python",
        "Repository contains visible test/spec-related files"
      ],
      "key_files": [],
      "relation_targets": [],
      "child_modules": []
    },
    {
      "name": "web",
      "path": "web",
      "category": "Web 前端",
      "responsibility": "提供浏览器侧界面、状态和交互能力。",
      "technologies": [],
      "key_files": [
        "web/index.html"
      ],
      "relation_targets": [],
      "child_modules": []
    }
  ],
  "module_layers": [
    {
      "name": "结构层",
      "purpose": "展示项目的顶层容器与运行边界，帮助先理解代码库的大框架。",
      "modules": [
        "desktop（package-or-app）",
        "docs（文档）",
        "examples（目录模块）",
        "src（源码根）",
        "tests（python-module）",
        "web（frontend）"
      ]
    }
  ],
  "key_relations": [],
  "build_steps": [
    {
      "label": "desktop:build",
      "command": "tauri build --no-bundle",
      "source": "desktop/package.json"
    },
    {
      "label": "desktop:build:installer",
      "command": "tauri build",
      "source": "desktop/package.json"
    },
    {
      "label": "desktop:dev",
      "command": "tauri dev",
      "source": "desktop/package.json"
    },
    {
      "label": "desktop:tauri",
      "command": "tauri",
      "source": "desktop/package.json"
    }
  ],
  "manifest_insights": [
    {
      "path": "desktop\\package-lock.json",
      "kind": "package-lock.json",
      "summary": [
        "{",
        "\"name\": \"aiwf-desktop\",",
        "\"version\": \"0.1.0\",",
        "\"lockfileVersion\": 3,",
        "\"requires\": true,"
      ]
    },
    {
      "path": "desktop\\package.json",
      "kind": "package.json",
      "summary": [
        "包名：aiwf-desktop",
        "Scripts: build, build:installer, dev, tauri",
        "Dependencies: none",
        "Dev dependencies: @tauri-apps/cli"
      ]
    },
    {
      "path": "desktop\\src-tauri\\Cargo.toml",
      "kind": "Cargo.toml",
      "summary": [
        "Crate 名称：aiwf-desktop",
        "Edition: 2021",
        "Dependencies: reqwest, serde, serde_json, tauri",
        "Binary targets: none"
      ]
    },
    {
      "path": "pyproject.toml",
      "kind": "pyproject.toml",
      "summary": [
        "Project name: ai-workflow-foundation",
        "Version: 0.1.0",
        "Dependencies: none",
        "Scripts: none"
      ]
    }
  ],
  "workflow_insights": [],
  "container_insights": [],
  "evaluation": {
    "project": {
      "project_weight_level": "L3",
      "project_weight_score": 51,
      "project_health_score": 88,
      "dimension_scores": {
        "scale": 65,
        "structural_complexity": 75,
        "dependency_complexity": 25,
        "operational_complexity": 45,
        "collaboration_complexity": 65,
        "change_impact": 20
      },
      "project_rationale": [
        "扫描了 8192 个文件，覆盖 6 个模块。",
        "检测到 2 种语言和 3 类运行时目标。",
        "观察到 0 条模块关系和 4 个构建步骤。",
        "项目负担最高的维度：结构复杂度。"
      ],
      "top_risks": [
        "多运行时目标会提升运维复杂度",
        "未检测到可见的 CI 文件"
      ],
      "recommended_priorities": []
    },
    "modules": [
      {
        "module_name": "desktop",
        "module_weight_level": "M4",
        "module_weight_score": 75,
        "maturity_level": "S5",
        "maturity_score": 81,
        "reliability_level": "R3",
        "reliability_score": 56,
        "extensibility_level": "E5",
        "extensibility_score": 87,
        "maintainability_level": "T5",
        "maintainability_score": 82,
        "dimension_breakdown": {
          "weight": {
            "score": 75,
            "level": "M4",
            "functional_criticality": 75,
            "dependency_centrality": 40,
            "change_risk": 80,
            "engineering_surface": 100,
            "cognitive_load": 100
          },
          "maturity": {
            "score": 81,
            "level": "S5",
            "boundary_clarity": 100,
            "documentation_quality": 90,
            "test_presence": 45,
            "delivery_guardrails": 80,
            "evolution_stability": 100
          },
          "reliability": {
            "score": 56,
            "level": "R3",
            "verifiability": 45,
            "error_handling": 60,
            "input_contracts": 50,
            "dependency_stability": 90,
            "regression_control": 45
          },
          "extensibility": {
            "score": 87,
            "level": "E5",
            "boundary_design": 100,
            "decoupling_quality": 85,
            "abstraction_quality": 85,
            "configuration_flexibility": 75,
            "replacement_cost": 85
          },
          "maintainability": {
            "score": 82,
            "level": "T5",
            "readability": 75,
            "consistency": 70,
            "local_reasoning": 90,
            "tooling_support": 75,
            "refactor_fitness": 100
          }
        },
        "evidence": [
          "路径：desktop",
          "类型：package-or-app",
          "文件数：7381",
          "传入关系：0；传出关系：0",
          "清单：desktop\\node_modules\\@tauri-apps\\cli-win32-x64-msvc\\package.json, desktop\\node_modules\\@tauri-apps\\cli\\package.json, desktop\\package.json",
          "文档：desktop\\README.md, desktop\\node_modules\\@tauri-apps\\cli-win32-x64-msvc\\README.md",
          "构建步骤：desktop:build, desktop:build:installer, desktop:dev"
        ],
        "evidence_by_axis": {
          "weight": [
            "路径：desktop",
            "类型：package-or-app",
            "传入关系：0；传出关系：0",
            "构建步骤数：4"
          ],
          "maturity": [
            "路径：desktop",
            "类型：package-or-app",
            "清单数量：4",
            "文档数量：10",
            "附近测试文件数：0"
          ],
          "reliability": [
            "路径：desktop",
            "类型：package-or-app",
            "附近测试文件数：0",
            "入口点数量：2",
            "依赖数量：1"
          ],
          "extensibility": [
            "路径：desktop",
            "类型：package-or-app",
            "本地依赖数：1",
            "对外源码关系数：0",
            "清单数量：4"
          ],
          "maintainability": [
            "路径：desktop",
            "类型：package-or-app",
            "文件数：7381",
            "主要扩展名：<no_ext>: 1956, .json: 903, .timestamp: 868",
            "文档数量：10"
          ]
        },
        "recommendations": [
          "补强该模块周边的测试、校验和失败处理"
        ]
      },
      {
        "module_name": "docs",
        "module_weight_level": "M2",
        "module_weight_score": 34,
        "maturity_level": "S3",
        "maturity_score": 57,
        "reliability_level": "R2",
        "reliability_score": 36,
        "extensibility_level": "E4",
        "extensibility_score": 65,
        "maintainability_level": "T5",
        "maintainability_score": 86,
        "dimension_breakdown": {
          "weight": {
            "score": 34,
            "level": "M2",
            "functional_criticality": 50,
            "dependency_centrality": 20,
            "change_risk": 20,
            "engineering_surface": 40,
            "cognitive_load": 40
          },
          "maturity": {
            "score": 57,
            "level": "S3",
            "boundary_clarity": 55,
            "documentation_quality": 90,
            "test_presence": 45,
            "delivery_guardrails": 45,
            "evolution_stability": 60
          },
          "reliability": {
            "score": 36,
            "level": "R2",
            "verifiability": 25,
            "error_handling": 45,
            "input_contracts": 30,
            "dependency_stability": 35,
            "regression_control": 45
          },
          "extensibility": {
            "score": 65,
            "level": "E4",
            "boundary_design": 55,
            "decoupling_quality": 85,
            "abstraction_quality": 65,
            "configuration_flexibility": 30,
            "replacement_cost": 85
          },
          "maintainability": {
            "score": 86,
            "level": "T5",
            "readability": 100,
            "consistency": 80,
            "local_reasoning": 90,
            "tooling_support": 75,
            "refactor_fitness": 80
          }
        },
        "evidence": [
          "路径：docs",
          "类型：文档",
          "文件数：3",
          "传入关系：0；传出关系：0",
          "文档：docs\\api.md, docs\\architecture.md"
        ],
        "evidence_by_axis": {
          "weight": [
            "路径：docs",
            "类型：文档",
            "传入关系：0；传出关系：0",
            "构建步骤数：0"
          ],
          "maturity": [
            "路径：docs",
            "类型：文档",
            "清单数量：0",
            "文档数量：3",
            "附近测试文件数：0"
          ],
          "reliability": [
            "路径：docs",
            "类型：文档",
            "附近测试文件数：0",
            "入口点数量：0",
            "依赖数量：0"
          ],
          "extensibility": [
            "路径：docs",
            "类型：文档",
            "本地依赖数：0",
            "对外源码关系数：0",
            "清单数量：0"
          ],
          "maintainability": [
            "路径：docs",
            "类型：文档",
            "文件数：3",
            "主要扩展名：.md: 3",
            "文档数量：3"
          ]
        },
        "recommendations": [
          "加强模块交付护栏和文档建设",
          "补强该模块周边的测试、校验和失败处理"
        ]
      },
      {
        "module_name": "examples",
        "module_weight_level": "M3",
        "module_weight_score": 42,
        "maturity_level": "S3",
        "maturity_score": 57,
        "reliability_level": "R2",
        "reliability_score": 36,
        "extensibility_level": "E4",
        "extensibility_score": 65,
        "maintainability_level": "T5",
        "maintainability_score": 84,
        "dimension_breakdown": {
          "weight": {
            "score": 42,
            "level": "M3",
            "functional_criticality": 50,
            "dependency_centrality": 20,
            "change_risk": 20,
            "engineering_surface": 80,
            "cognitive_load": 60
          },
          "maturity": {
            "score": 57,
            "level": "S3",
            "boundary_clarity": 55,
            "documentation_quality": 90,
            "test_presence": 45,
            "delivery_guardrails": 45,
            "evolution_stability": 60
          },
          "reliability": {
            "score": 36,
            "level": "R2",
            "verifiability": 25,
            "error_handling": 45,
            "input_contracts": 30,
            "dependency_stability": 35,
            "regression_control": 45
          },
          "extensibility": {
            "score": 65,
            "level": "E4",
            "boundary_design": 55,
            "decoupling_quality": 85,
            "abstraction_quality": 65,
            "configuration_flexibility": 30,
            "replacement_cost": 85
          },
          "maintainability": {
            "score": 84,
            "level": "T5",
            "readability": 90,
            "consistency": 80,
            "local_reasoning": 90,
            "tooling_support": 75,
            "refactor_fitness": 80
          }
        },
        "evidence": [
          "路径：examples",
          "类型：目录模块",
          "文件数：11",
          "传入关系：0；传出关系：0",
          "文档：examples\\skills\\module_mapping.SKILL.md, examples\\skills\\unity_build_plan.SKILL.md"
        ],
        "evidence_by_axis": {
          "weight": [
            "路径：examples",
            "类型：目录模块",
            "传入关系：0；传出关系：0",
            "构建步骤数：0"
          ],
          "maturity": [
            "路径：examples",
            "类型：目录模块",
            "清单数量：0",
            "文档数量：3",
            "附近测试文件数：0"
          ],
          "reliability": [
            "路径：examples",
            "类型：目录模块",
            "附近测试文件数：0",
            "入口点数量：0",
            "依赖数量：0"
          ],
          "extensibility": [
            "路径：examples",
            "类型：目录模块",
            "本地依赖数：0",
            "对外源码关系数：0",
            "清单数量：0"
          ],
          "maintainability": [
            "路径：examples",
            "类型：目录模块",
            "文件数：11",
            "主要扩展名：.json: 8, .md: 3",
            "文档数量：3"
          ]
        },
        "recommendations": [
          "加强模块交付护栏和文档建设",
          "补强该模块周边的测试、校验和失败处理"
        ]
      },
      {
        "module_name": "src",
        "module_weight_level": "M3",
        "module_weight_score": 40,
        "maturity_level": "S3",
        "maturity_score": 46,
        "reliability_level": "R2",
        "reliability_score": 33,
        "extensibility_level": "E4",
        "extensibility_score": 62,
        "maintainability_level": "T4",
        "maintainability_score": 73,
        "dimension_breakdown": {
          "weight": {
            "score": 40,
            "level": "M3",
            "functional_criticality": 50,
            "dependency_centrality": 20,
            "change_risk": 20,
            "engineering_surface": 80,
            "cognitive_load": 40
          },
          "maturity": {
            "score": 46,
            "level": "S3",
            "boundary_clarity": 55,
            "documentation_quality": 35,
            "test_presence": 45,
            "delivery_guardrails": 45,
            "evolution_stability": 50
          },
          "reliability": {
            "score": 33,
            "level": "R2",
            "verifiability": 25,
            "error_handling": 35,
            "input_contracts": 30,
            "dependency_stability": 35,
            "regression_control": 45
          },
          "extensibility": {
            "score": 62,
            "level": "E4",
            "boundary_design": 55,
            "decoupling_quality": 85,
            "abstraction_quality": 50,
            "configuration_flexibility": 30,
            "replacement_cost": 85
          },
          "maintainability": {
            "score": 73,
            "level": "T4",
            "readability": 70,
            "consistency": 65,
            "local_reasoning": 90,
            "tooling_support": 75,
            "refactor_fitness": 65
          }
        },
        "evidence": [
          "路径：src",
          "类型：源码根",
          "文件数：11",
          "传入关系：0；传出关系：0"
        ],
        "evidence_by_axis": {
          "weight": [
            "路径：src",
            "类型：源码根",
            "传入关系：0；传出关系：0",
            "构建步骤数：0"
          ],
          "maturity": [
            "路径：src",
            "类型：源码根",
            "清单数量：0",
            "文档数量：0",
            "附近测试文件数：0"
          ],
          "reliability": [
            "路径：src",
            "类型：源码根",
            "附近测试文件数：0",
            "入口点数量：0",
            "依赖数量：0"
          ],
          "extensibility": [
            "路径：src",
            "类型：源码根",
            "本地依赖数：0",
            "对外源码关系数：0",
            "清单数量：0"
          ],
          "maintainability": [
            "路径：src",
            "类型：源码根",
            "文件数：11",
            "主要扩展名：.py: 11",
            "文档数量：0"
          ]
        },
        "recommendations": [
          "加强模块交付护栏和文档建设",
          "补强该模块周边的测试、校验和失败处理"
        ]
      },
      {
        "module_name": "tests",
        "module_weight_level": "M3",
        "module_weight_score": 44,
        "maturity_level": "S4",
        "maturity_score": 60,
        "reliability_level": "R3",
        "reliability_score": 55,
        "extensibility_level": "E4",
        "extensibility_score": 62,
        "maintainability_level": "T4",
        "maintainability_score": 73,
        "dimension_breakdown": {
          "weight": {
            "score": 44,
            "level": "M3",
            "functional_criticality": 70,
            "dependency_centrality": 20,
            "change_risk": 20,
            "engineering_surface": 80,
            "cognitive_load": 40
          },
          "maturity": {
            "score": 60,
            "level": "S4",
            "boundary_clarity": 55,
            "documentation_quality": 35,
            "test_presence": 100,
            "delivery_guardrails": 45,
            "evolution_stability": 50
          },
          "reliability": {
            "score": 55,
            "level": "R3",
            "verifiability": 60,
            "error_handling": 55,
            "input_contracts": 45,
            "dependency_stability": 35,
            "regression_control": 80
          },
          "extensibility": {
            "score": 62,
            "level": "E4",
            "boundary_design": 55,
            "decoupling_quality": 85,
            "abstraction_quality": 50,
            "configuration_flexibility": 30,
            "replacement_cost": 85
          },
          "maintainability": {
            "score": 73,
            "level": "T4",
            "readability": 70,
            "consistency": 65,
            "local_reasoning": 90,
            "tooling_support": 75,
            "refactor_fitness": 65
          }
        },
        "evidence": [
          "路径：tests",
          "类型：python-module",
          "文件数：8",
          "传入关系：0；传出关系：0",
          "模块附近检测到的测试文件数：8"
        ],
        "evidence_by_axis": {
          "weight": [
            "路径：tests",
            "类型：python-module",
            "传入关系：0；传出关系：0",
            "构建步骤数：0"
          ],
          "maturity": [
            "路径：tests",
            "类型：python-module",
            "清单数量：0",
            "文档数量：0",
            "附近测试文件数：8"
          ],
          "reliability": [
            "路径：tests",
            "类型：python-module",
            "附近测试文件数：8",
            "入口点数量：0",
            "依赖数量：0"
          ],
          "extensibility": [
            "路径：tests",
            "类型：python-module",
            "本地依赖数：0",
            "对外源码关系数：0",
            "清单数量：0"
          ],
          "maintainability": [
            "路径：tests",
            "类型：python-module",
            "文件数：8",
            "主要扩展名：.py: 8",
            "文档数量：0"
          ]
        },
        "recommendations": [
          "补强该模块周边的测试、校验和失败处理"
        ]
      },
      {
        "module_name": "web",
        "module_weight_level": "M2",
        "module_weight_score": 34,
        "maturity_level": "S3",
        "maturity_score": 46,
        "reliability_level": "R2",
        "reliability_score": 33,
        "extensibility_level": "E4",
        "extensibility_score": 65,
        "maintainability_level": "T4",
        "maintainability_score": 75,
        "dimension_breakdown": {
          "weight": {
            "score": 34,
            "level": "M2",
            "functional_criticality": 65,
            "dependency_centrality": 20,
            "change_risk": 20,
            "engineering_surface": 20,
            "cognitive_load": 40
          },
          "maturity": {
            "score": 46,
            "level": "S3",
            "boundary_clarity": 55,
            "documentation_quality": 35,
            "test_presence": 45,
            "delivery_guardrails": 45,
            "evolution_stability": 50
          },
          "reliability": {
            "score": 33,
            "level": "R2",
            "verifiability": 25,
            "error_handling": 35,
            "input_contracts": 30,
            "dependency_stability": 35,
            "regression_control": 45
          },
          "extensibility": {
            "score": 65,
            "level": "E4",
            "boundary_design": 55,
            "decoupling_quality": 85,
            "abstraction_quality": 65,
            "configuration_flexibility": 30,
            "replacement_cost": 85
          },
          "maintainability": {
            "score": 75,
            "level": "T4",
            "readability": 80,
            "consistency": 65,
            "local_reasoning": 90,
            "tooling_support": 75,
            "refactor_fitness": 65
          }
        },
        "evidence": [
          "路径：web",
          "类型：frontend",
          "文件数：1",
          "传入关系：0；传出关系：0"
        ],
        "evidence_by_axis": {
          "weight": [
            "路径：web",
            "类型：frontend",
            "传入关系：0；传出关系：0",
            "构建步骤数：0"
          ],
          "maturity": [
            "路径：web",
            "类型：frontend",
            "清单数量：0",
            "文档数量：0",
            "附近测试文件数：0"
          ],
          "reliability": [
            "路径：web",
            "类型：frontend",
            "附近测试文件数：0",
            "入口点数量：0",
            "依赖数量：0"
          ],
          "extensibility": [
            "路径：web",
            "类型：frontend",
            "本地依赖数：0",
            "对外源码关系数：0",
            "清单数量：0"
          ],
          "maintainability": [
            "路径：web",
            "类型：frontend",
            "文件数：1",
            "主要扩展名：.html: 1",
            "文档数量：0"
          ]
        },
        "recommendations": [
          "加强模块交付护栏和文档建设",
          "补强该模块周边的测试、校验和失败处理"
        ]
      }
    ]
  },
  "key_files": [
    "desktop\\node_modules\\@tauri-apps\\cli\\index.js",
    "desktop\\node_modules\\@tauri-apps\\cli\\main.js",
    "desktop\\node_modules\\@tauri-apps\\cli-win32-x64-msvc\\package.json",
    "desktop\\node_modules\\@tauri-apps\\cli\\package.json",
    "desktop\\package.json",
    "desktop\\src-tauri\\Cargo.toml",
    "docs\\api.md",
    "docs\\architecture.md",
    "docs\\delivery.md",
    "examples\\skills\\module_mapping.SKILL.md",
    "examples\\skills\\unity_build_plan.SKILL.md",
    "examples\\skills\\unity_requirement_analysis.SKILL.md"
  ],
  "deep_dive_notes": [],
  "open_questions": [
    "缺少 CI 工作流证据，交付方式和质量门禁可能不完整。",
    "模块关系较少，关键调用链可能尚未被静态规则完整识别。"
  ]
}
```

