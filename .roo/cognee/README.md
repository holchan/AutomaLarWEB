# **Knowledge Graph Data Layer Blueprint (V3 - Final)**

### **1. Executive Summary & Core Philosophy**

#### **i. The Guiding Principle: "Progressive Enrichment of Provable Truth"**

At its heart, this system creates a living, queryable **"digital brain"** for a repository. Its purpose is not just to parse files, but to understand *how* and *why* code connects. After a rigorous process of design, debate, and refinement, we have established a core philosophy founded on a deep skepticism of "magic" solutions and a commitment to building a system that is, above all, **trustworthy**.

This philosophy rests on four foundational pillars:
1.  **The Focused Expert Reporter (Parser's Role):** Each parser is a master of a single language's syntax. Its only job is to report facts (`CodeEntity` definitions) and evidence (`RawSymbolReference`) from a single file. It does not link or guess.
2.  **Centralized Intelligence (Orchestrator's Role):** A language-agnostic `Orchestrator` consumes these reports and performs only the highest-confidence, real-time linking tasks (Tier 1). It creates "debt" (`PendingLink` nodes) for everything else.
3.  **On-Demand, Event-Driven Enrichment (Dispatcher's Role):** We have **rejected** the model of inefficient, always-on background workers. Instead, a stateful but efficient `Dispatcher` listens for ingestion activity. Only after a repository has been inactive for a configurable period does it trigger the resource-intensive Tier 2 (Heuristic) and Tier 3 (LLM) enhancement tasks.
4.  **Database as a First-Class Partner (Neo4j):** We have committed to **Neo4j** as our backend. This allows us to leverage the power of the Cypher query language for advanced linking heuristics (`ENDS WITH`) and to ensure performance through programmatic index management, making the system self-configuring and scalable.

#### **ii. System Benefits and Guarantees**

This architecture provides a clear set of guarantees that define its behavior and value.

##### **Reliability Guarantees**
- **Atomic & Resilient Transactions:** Every file processing operation is wrapped in a transaction with an automatic, `tenacity`-based retry mechanism for transient database errors.
- **Provable Idempotency:** The system uses a `content_hash` check to guarantee that the exact same file content is never processed more than once, preventing data duplication.
- **Race-Condition-Proof Versioning:** An atomic, database-side counter ensures that multiple concurrent operations on the same file path produce correct, sequential versions without conflict.
- **Verifiable Truth:** The system will **never create a relationship it cannot prove.** An unresolved link (`PendingLink`) is infinitely preferred over an incorrect one. The LLM is used as a "hint generator," but its suggestions are always verified against the graph's ground truth before a link is created.

##### **Performance & Efficiency Characteristics**
- **Real-Time Ingestion (Tier 1):** The primary ingestion path is extremely fast, deferring all complex and slow operations.
- **On-Demand Asynchronous Enrichment (Tiers 2-3):** Expensive heuristic and LLM-based linking tasks are only triggered by the `Dispatcher` when a repository is quiescent, ensuring they never block real-time ingestion and that system resources are used efficiently.
- **Intelligent Caching:** A `ResolutionCache` ensures that once an expensive question (especially an LLM query) is answered and verified, it is never asked again.
- **Performant by Design:** The system automatically ensures all necessary database indexes exist before running enhancement queries, guaranteeing fast lookups on our chosen **Neo4j** backend.

##### **Scalability & Extensibility Features**
- **Language Agnostic:** The "Focused Expert Reporter" pattern allows new languages to be added simply by creating a new parser that adheres to the `BaseParser` contract. No other system components need to be changed.
- **Robust Fallbacks:** A centralized fallback mechanism in the `Orchestrator` ensures that even non-code files (like documentation or comment-only files) are intelligently chunked and ingested using a `GenericParser`, guaranteeing complete repository coverage.
- **Single-Instance Scaling (Current Scope):** The current architecture is designed for a robust, highly-performant single service instance. Horizontal scaling to multiple replicas is a V2 consideration that will require a distributed locking mechanism.

#### **iii. The Relationship Catalog: Describing the "Knowledge" in the Graph**

The ultimate goal of this system is to produce a rich, queryable set of `Relationship` nodes. These edges are what transform a disconnected collection of files and text into a true knowledge graph. Each relationship type is designed to answer a specific, high-value question a developer would ask about the codebase.

The relationships are created at different stages by different system components, based on the level of confidence and context required.

---

#### **Category 1: Structural & Foundational Relationships (The "Where")**

These relationships form the physical and logical backbone of the graph. They are unambiguous and are created with **100% confidence** by the **Orchestrator** during its real-time, Tier 1 processing.

**`CONTAINS_CHUNK`**
*   **Direction:** `(SourceFile) -> [CONTAINS_CHUNK] -> (TextChunk)`
*   **Purpose:** Describes the physical hierarchy of a file. It answers: "What are the constituent text blocks of this specific version of this file?"
*   **Creation:** The `Orchestrator` creates these immediately after the `generate_intelligent_chunks` function runs.

**`DEFINES_CODE_ENTITY`**
*   **Direction:** `(TextChunk) -> [DEFINES_CODE_ENTITY] -> (CodeEntity)`
*   **Purpose:** Links a specific piece of code to the text block where it is defined. It answers: "In which part of `main.py` is the `run()` function actually located?"
*   **Creation:** The `Orchestrator` creates these after finalizing a `CodeEntity`'s permanent ID by mapping it to its parent `TextChunk`.

**`INCLUDE`**
*   **Direction:** `(SourceFile) -> [INCLUDE] -> (SourceFile)`
*   **Purpose:** Models a direct, file-level include (`#include "..."`). This is fundamental for dependency tracking. It answers: "What other local header files does `main.cpp` depend on?"
*   **Creation:** Created by the Tier 1 `Orchestrator` if a parser yields a `RawSymbolReference` for a *relative* include, which can be resolved immediately.

---

#### **Category 2: High-Confidence Semantic Relationships (The "How")**

These relationships describe how code elements interact. They are created with very high confidence by the deterministic tiers of our system.

**`EXTENDS` / `IMPLEMENTS`**
*   **Direction:** `(Child Class: CodeEntity) -> [EXTENDS] -> (Parent Class: CodeEntity)`
*   **Purpose:** Models the inheritance hierarchy, fundamental to OOP. It answers: "What is the parent class of `MyExtendedClass`?"
*   **Creation:** Created by the Tier 2 `GraphEnhancementEngine` when its exact-match or verified suffix-match heuristics find an unambiguous parent.

**`CALLS`**
*   **Direction:** `(Calling Function: CodeEntity) -> [CALLS] -> (Called Function: CodeEntity)`
*   **Purpose:** This is the most important relationship for understanding runtime behavior. It answers: "Who calls the `calculate_total()` function?"
*   **Creation:**
    *   **Tier 2:** The `GraphEnhancementEngine` creates this link when its deterministic heuristics find a single, unambiguous target for a function call.
    *   **Tier 3:** The `GraphEnhancementEngine` creates this link after an LLM provides a hint for an ambiguous call, and that hint has been **verified** to exist in the graph. The relationship metadata will indicate it was AI-assisted.

**`IMPORTS`**
*   **Direction:** `(CodeEntity) -> [IMPORTS] -> (CodeEntity)`
*   **Purpose:** Models a specific symbol import (e.g., Python's `from .utils import helper`). This is more granular than a file-level include. It answers: "Which function specifically imports the `helper` function?"
*   **Creation:** Created by the Tier 2 `GraphEnhancementEngine` when it can resolve a specific import reference.

---

#### **Category 3: Inferred & Abstract Relationships (The "Hidden How")**

These relationships capture dependencies that are not direct calls or inheritance, or that are intentionally abstract.

**`USES_LIBRARY`**
*   **Direction:** `(SourceFile) -> [USES_LIBRARY] -> (ExternalReference)`
*   **Purpose:** Creates a high-level, factual link to an external dependency *without* resolving the specific function call. This is a fast, 100% confident statement that a dependency *exists*. It answers: "Which files in my project have a dependency on the `pandas` library?"
*   **Creation:** Created by the Tier 1 `Orchestrator`. When it receives a `RawSymbolReference` for an absolute import (`#include <vector>`, `import pandas`) and cannot resolve it internally, it creates this link to a canonical `ExternalReference` node (e.g., `external://pandas`).

**`REFERENCES_SYMBOL`**
*   **Direction:** `(CodeEntity) -> [REFERENCES_SYMBOL] -> (CodeEntity or ExternalReference)`
*   **Purpose:** To capture "weaker" connections that aren't direct calls, inheritance, or imports. This is our solution for tracking dependencies inside C++ macros. It answers: "What other symbols does this macro depend on?"
*   **Creation:** Primarily created by the Tier 2 or Tier 3 `GraphEnhancementEngine` when it resolves a reference of type `REFERENCES_SYMBOL` that was yielded by a parser (e.g., for a symbol used inside a macro argument).

---

### **2. Foundational Architecture Principles**

Our entire system is built upon four foundational pillars. These principles, forged through a rigorous process of design and debate, guide every component and ensure the final graph is trustworthy, maintainable, and efficient.

#### **Pillar 1: The Focused Expert (The Parser's Role)**

*   **What It Is:** Each parser is a **"Sufficient Context Reporter."** It is a master of a single language's syntax. Its only job is to analyze the Abstract Syntax Tree (AST) of a single file and report facts. It is a master of syntax, not cross-file semantics.
*   **The Context & Why It's Crucial:** We realized that building linking logic (e.g., "what file does this `#include` point to?") inside every single parser would be a nightmare of duplicated, fragile code. Instead, we radically simplify the parser's role. It doesn't link; it **reports**. It yields `CodeEntity` objects for definitions and rich, structured `RawSymbolReference` objects for any reference it finds. This report is its "dossier" on the reference, containing every contextual clue it can gather *from within that single file*.
*   **The Analogy:** The parser is an **expert witness at a crime scene**. It doesn't solve the case. It perfectly and factually reports: "I found these footprints, of this size, pointing in this direction. I also found these fingerprints on the doorknob."

#### **Pillar 2: Centralized Intelligence (The Orchestrator's Role)**

*   **What It Is:** The `Orchestrator` is the **"Tier 1 Real-Time Engine."** It is completely language-agnostic. Its only job is to consume the standardized reports from any parser and apply a fast, simple, and deterministic set of rules.
*   **The Context & Why It's Crucial:** This solves the maintainability problem by centralizing all ingestion logic. The Orchestrator's key responsibility is **speed**. It performs only the highest-confidence actions: creating nodes, handling file versioning, and resolving only the most certain links (like a direct relative import). For everything else, it creates a `PendingLink` "debt" node, honestly acknowledging what it doesn't know yet.
*   **The Analogy:** The Orchestrator is the **triage unit in an emergency room**. It handles the simple cases immediately, stabilizes the patient (the graph), and correctly identifies the complex cases that need to be sent to a specialist for later analysis.

#### **Pillar 3: On-Demand, Event-Driven Enrichment (The Dispatcher's Role)**

*   **What It Is:** This is the most significant evolution of our architecture. We have **explicitly rejected** the inefficient model of always-on background workers. Instead, a stateful but efficient **`Dispatcher`** acts as the system's central nervous system.
*   **The Context & Why It's Crucial:** This solves the "expensive operation" problem with maximum efficiency. The `Orchestrator` notifies the `Dispatcher` of any file activity. The `Dispatcher` then starts a per-repository **quiescence timer**. Only when a repository has been inactive for a configured period does it dispatch the resource-intensive Tier 2 and Tier 3 enhancement tasks. This ensures that heavy processing only happens when needed, never blocking real-time ingestion.
*   **The Analogy:** The `Dispatcher` is the **air traffic controller**. It sees planes landing (ingestion activity) and safely holds the large, slow-moving cargo planes (the enhancement tasks) in a holding pattern. Only when the runway is clear for a while does it give them permission to land.

#### **Pillar 4: Provable Truth & Database Partnership (The Engine's Role)**

*   **What It Is:** This is our most important philosophical stance, executed by the **`GraphEnhancementEngine`**. The system will **never create a relationship it cannot prove.** A missing link is infinitely better than an incorrect one.
*   **The Context & Why It's Crucial:**
    1.  **Provable Truth:** The Tier 2 engine uses deterministic heuristics (exact match, verified suffix match). It only creates a link if it finds **exactly one** unambiguous answer.
    2.  **Verified LLM Hints:** The Tier 3 engine uses the LLM as an intelligent "hint generator," not a final authority. The LLM's suggested `canonical_fqn` is **always verified** against the graph. A link is only created if the suggestion is proven to exist.
    3.  **Database Partnership:** We have committed to **Neo4j**, allowing the `GraphEnhancementEngine` to use powerful, native Cypher queries (`ENDS WITH`) for its heuristics, ensuring high performance. The system is also self-managing, as the `Dispatcher` ensures all necessary database indexes are created before these queries run.
*   **The Analogy:** The `GraphEnhancementEngine` is the **team of specialist detectives**. They receive the complex cases from triage. The Tier 2 detective solves cases with definitive forensic evidence. The Tier 3 detective consults an informant (the LLM) for a lead, but then must independently find concrete proof (verify the hint against the graph) before making an arrest (creating a link).

---

### **3. Data Contracts (`entities.py`): The Universal Language**

This file is the most critical piece of the entire project. It is the **formal, typed contract** that defines how our disparate components communicate. It is the single source of truth for the structure of all data that flows through the system.

#### **i. The Core Philosophy of Our Data Contracts**

The principle behind these data models is to **separate factual reporting from interpretive resolution.**
*   **Parsers are "Witnesses":** They are experts on syntax and report only what they can see in a single file, yielding `CodeEntity` and `RawSymbolReference` objects.
*   **The Orchestrator and Enhancement Engine are "Detectives":** They interpret the evidence from the parsers to build the final graph, using `PendingLink` and `ResolutionCache` to manage the complex, asynchronous process of solving the case.

Every model and field has been refined to be as robust and universally applicable as possible, incorporating key decisions about our architecture.

#### **ii. The Input Contract: `FileProcessingRequest`**

This is the sole input to the system. It is a self-contained work order for a single file.

*   **Key Fields (Finalized):**
    *   `absolute_path: str`: The full path to the file on disk.
    *   `repo_path: str`: The path to the repository root.
    *   `repo_id: str`: The repository identifier (e.g., `automalar/automalarweb`).
    *   `branch: str`: The branch name (e.g., `main`).
    *   **`commit_index: int = 1`**: The commit sequence number. **defaults to `1`** for easier use, optional.
    *   **`is_delete: bool = False`**: Flag for `DELETE` operations. **defaults to `False`** (UPSERT), optional.
    *   `import_id: Optional[str]`: The canonical name if the repo is a library (e.g., `pandas`), optional.
    *   `root_namespace: Optional[str]`: The root namespace for languages like Java (e.g., `com.mycompany.project`), optional.

#### **iii. The Core Graph Models: ID and Data Philosophy**

This section defines the final structure of our graph nodes, reflecting our decisions on ID formatting and data representation.

*   **Design Philosophy:** Prioritize queryability and explicit, human-readable data.
*   **The `id` field is the `slug_id`:** This is our human-readable, globally unique primary key. It is indexed for fast lookups.
*   **ID Formatting (Finalized):**
    *   **No Zero-Padding:** All numerical components in IDs (commit index, save count, line numbers) will be standard integers, not zero-padded strings.
    *   **1-Based Numbers:** All user-facing numbers (lines, versions) are 1-based to match developer intuition.

*   **`Repository`**
    *   `id`: `"<repo_id>@<branch>"`
    *   **Example:** `"automalar/automalarweb@main"`

*   **`SourceFile`**
    *   `id`: `"<repository_id>|<relative_path>@<commit_index>-<local_save>"`
    *   **Example:** `"automalar/automalarweb@main|src/main.py@12-3"`

*   **`TextChunk`**
    *   `id`: `"<source_file_id>|<chunk_index>@<start_line>-<end_line>"`
    *   **Example:** `"...|src/main.py@12-3|0@1-10"`

*   **`CodeEntity`**
    *   `id`: `"<text_chunk_id>|<local_fqn>@<start_line>-<end_line>"`
    *   **Example:** `"...|0@1-10|MyClass::my_method@5-8"`
    *   **Key Fields (Finalized):**
        *   `start_line: int`, `end_line: int`: **1-based** line numbers.
        *   `canonical_fqn: Optional[str]`: The parser's best-effort canonical FQN. This is a critical, indexed field for linking.
        *   **`metadata: Optional[Dict[str, Any]]`**: An optional field to store extra context, such as conditional compilation flags.

#### **iv. The Universal Report: `RawSymbolReference` and `ReferenceContext`**

This is the standardized "forensic report" from every parser.

*   **`RawSymbolReference`**
    *   **`metadata: Optional[Dict[str, Any]]`**: **(New)** An optional field, parallel to `CodeEntity`, for storing context like conditional compilation.

*   **`ReferenceContext`**
    *   **`import_type: ImportType`**: The crucial `RELATIVE` vs. `ABSOLUTE` distinction.
    *   **`path_parts: List[str]`**: The sequence of names in an import path.

#### **v. The Asynchronous State Machine: `PendingLink` and `ResolutionCache`**

These are the bookkeeping tools that enable our **"On-Demand, Event-Driven Enrichment"** philosophy.

*   **`LinkStatus` (The Workflow Engine - Finalized):**
    *   `PENDING_RESOLUTION`: Initial state, created by the `Orchestrator`.
    *   `READY_FOR_HEURISTICS`: Promoted by the `Dispatcher` after quiescence.
    *   `READY_FOR_LLM`: Promoted by the Tier 2 engine if heuristics fail or are ambiguous.
    *   `AWAITING_TARGET`: Set by the Tier 3 engine after receiving an LLM hint, waiting for the target entity to be created.
    *   `UNRESOLVABLE`: A terminal failure state.
    *   `ENHANCEMENT_FAILED`: **(New)** A terminal failure state set by the `Dispatcher` if an entire enhancement cycle fails due to an unrecoverable error.

*   **Context and Rationale (Updated):** The `LinkStatus` enum is the state machine that drives our entire asynchronous process. The `Dispatcher` now controls the promotion from `PENDING_RESOLUTION` to `READY_FOR_HEURISTICS`, replacing the old "Janitor" logic. The `AWAITING_TARGET` status is the key to our robust "Consult, Verify, Cache" LLM workflow.

---

### **Component A: The Parser - The "Sufficient Context Reporter"**

#### **i. Core Philosophy**

The single most important architectural decision we made was to redefine the parser's job. It is not a "linker" or a "guesser." It is a **Focused Expert Reporter.** Its responsibility is to be the world's leading expert on the syntax of a single file for a single language. It makes **zero assumptions** about any other file, repository, or the state of the graph. It is a stateless, pure function that transforms source code text into a stream of high-fidelity, factual data.

Its contract is to yield only three types of objects:
1.  **A `List[int]` of `slice_lines`:** Its best advice on where to semantically chunk the file.
2.  **`CodeEntity` objects:** Factual reports of every definition (class, function, etc.) it finds.
3.  **`RawSymbolReference` objects:** Rich, evidential reports of every reference (a call, import, etc.) it finds, complete with all surrounding syntactic context.

Crucially, **it never yields `Relationship` objects.** This strict separation of concerns is the key to our system's maintainability and extensibility.

#### **ii. Finalized Parser Responsibilities**

1.  **Yield `slice_lines`**
    *   **Action:** The parser identifies all top-level definition nodes (classes, functions, etc.). It yields a single `List[int]` containing the **1-based** starting line number of each of these definitions.
    *   **Guaranteeing Full Coverage:** If any definitions are found, the parser **must** ensure that the number `1` is included in the returned list. This guarantees that content at the top of the file (like file-level comments or imports) is included in the first chunk.
    *   **The Fallback Signal:** If a parser runs on a non-empty file but finds **zero** code definitions (e.g., a comment-only file, a markdown file), it correctly yields an **empty list `[]`**. This is the crucial, intentional signal that tells the `Orchestrator` to use the `GenericParser` fallback for token-based chunking.

2.  **Yield `CodeEntity`**
    *   **Action:** Using its language-specific Tree-sitter queries, the parser identifies every single definition of a class, struct, function, enum, macro, lambda, etc.
    *   **The Temporary ID (`FQN@line`):** The `id` field of the yielded `CodeEntity` is a temporary string like `"MyNamespace::MyClass@51"`. The `@line` part is a **1-based** line number, which the Orchestrator uses to map the entity to its final parent `TextChunk`.
    *   **Rich Data:** The parser populates the `canonical_fqn` field with its best-effort, language-specific Fully Qualified Name. It must also populate the optional `metadata` dictionary with any extra context it can gather, such as conditional compilation flags (e.g., `{'is_conditional': True, 'condition': '#ifdef DEBUG'}`).

3.  **Yield `RawSymbolReference`**
    *   **Action:** This is the parser's most sophisticated job. For every include, inheritance, function call, type annotation, or macro usage, it must yield a `RawSymbolReference`.
    *   **The `FileContext` (Internal Symbol Table):** To accomplish this, a high-quality parser (like our `CppParser`) builds an in-memory `FileContext` during its single AST walk. This symbol table is the parser's short-term memory, tracking the file's local context:
        *   What headers have been included and their aliases (`import_map`).
        *   What `using namespace` directives are active in the current scope (`active_usings`).
        *   The data types of locally declared variables (`local_variable_types`).
    *   **The `_resolve_context_for_reference` Helper:** When a reference is found, the parser uses its rich `FileContext` to perform a prioritized lookup and generate the most accurate possible `ReferenceContext` object. This provides the linking engine with high-quality, verifiable evidence, rather than just a simple string.

#### **iii. Known Limitations and Conscious Compromises**

This architecture is robust because it is honest about its limitations. We have made several conscious trade-offs to prioritize speed, simplicity, and language-agnosticism over perfect, compiler-level accuracy.

*   **Syntactic, Not Semantic, Analysis:** The system operates on the code **as written**, not as a compiler would interpret it. This is a fundamental design choice.
    *   **Conditional Compilation:** We now capture code within `#ifdef` blocks and can attach metadata to the resulting nodes (e.g., `{'is_conditional': True}`). However, the system does not evaluate the conditions to determine which code paths are active in a given build. It represents all possible paths.
    *   **Macro Expansion:** The system identifies macro definitions (`MacroDefinition`) and calls (`MACRO_CALL`). It even captures symbols referenced within macro arguments (`REFERENCES_SYMBOL`). It does **not**, however, perform macro expansion. We will not see the code that results from a macro. Requiring a C++ pre-processing step was deemed an unacceptable complexity.
    *   **Advanced Language Features:** The parser's FQN generation is a powerful heuristic based on AST traversal. It will not perfectly resolve names in all cases of advanced language features like C++ Argument-Dependent Lookup (ADL). This is an acceptable trade-off to avoid building a full, stateful compiler for each language.

*   **Wildcard Imports are Not Resolved:** For languages like Python, we explicitly do not support resolving symbols imported via wildcards (e.g., `from .utils import *`). The parser cannot provide sufficient context for these, and our core principle is to **never guess**. Such references will result in an unresolved `PendingLink`.

---

### **Component B: The Orchestrator (`orchestrator.py`)**

#### **i. Core Philosophy: The "Tier 1 Real-Time Engine"**

The Orchestrator's philosophy is one of **Speed, Safety, and Honesty**. It is a language-agnostic, real-time processor for a single file. Its primary goal is to get a file's data into the graph quickly and atomically, deferring all complex or slow operations. It acts as the central hub of our real-time ingestion pipeline.

#### **ii. Finalized Orchestrator Workflow**

The `process_single_file` function is the main entry point and is wrapped in a `tenacity`-based retry mechanism to handle transient database errors. The entire operation is a single, atomic transaction.

1.  **Input Validation & Robust Loading:**
    *   **Action:** It first validates the incoming `FileProcessingRequest` to ensure it's well-formed and the target file exists. On application startup, it also verifies that all critical parser modules have loaded correctly, failing fast if they have not.
    *   **Rationale:** This prevents the system from attempting to process invalid requests or starting in a broken state.

2.  **Handle Trivial Cases (Delete/Empty):**
    *   **Action:** It handles `DELETE` requests or empty/whitespace-only files. For a `DELETE`, it removes all nodes associated with the file path. For an empty file, it creates a single `SourceFile` node to represent its existence and then stops.
    *   **Rationale:** This efficiently handles simple cases without invoking the entire parsing and chunking pipeline.

3.  **Idempotency & Versioning:**
    *   **Action:**
        1.  It calculates a `content_hash` and checks if a `SourceFile` with that hash already exists. If so, it stops immediately, guaranteeing idempotency.
        2.  It calls the atomic `graph_utils.atomic_get_and_increment_local_save` function. This database-side operation is **race-condition-proof** and returns the next sequential version number for the file at that commit.
        3.  The final `version_id` is a clean, non-zero-padded string (e.g., `12-3`).
    *   **Rationale:** This two-pronged approach is highly robust. The hash prevents duplicate data globally, while the atomic counter safely handles versioning during concurrent operations.

4.  **Parse & Centralized Fallback:**
    *   **Action:** It calls the appropriate language-specific parser. It then implements our crucial fallback logic: **if the parser returns an empty `slice_lines` list for a non-empty file, it immediately calls the `GenericParser`** to re-process the file and generate token-based `slice_lines`.
    *   **Rationale:** This elegant design ensures that comment-only files or other non-code documents are still intelligently chunked and ingested without requiring complex logic inside every language parser.

5.  **Assemble Graph "Island":**
    *   **Action:** It takes the final `slice_lines` and calls the `generate_intelligent_chunks` function. It then creates all `Repository`, `SourceFile`, `TextChunk`, and `CodeEntity` nodes, along with their structural relationships (`CONTAINS_CHUNK`, `DEFINES_CODE_ENTITY`). It is the sole authority for creating the final, permanent, human-readable IDs for all nodes based on our 1-based numbering scheme.
    *   **Rationale:** This step builds the entire self-contained "island" of graph data for the file in a single, atomic operation.

6.  **Tier 1 Resolution & "Debt" Creation:**
    *   **Action:** It iterates through the `RawSymbolReference`s from the parser. It attempts to resolve only the highest-confidence links—both relative and absolute imports—by calling the optimized `graph_utils.find_code_entity_by_path`.
    *   **Outcome:** If a link is resolved, a `Relationship` is created. For all others, a `PendingLink` "debt" node is created, honestly capturing what the system does not yet know.
    *   **Rationale:** This maintains the speed of the real-time pipeline by deferring all non-trivial linking decisions.

7.  **Final Commit & Dispatch:**
    *   **Action:** After the database transaction successfully commits, it calls `dispatcher.notify_ingestion_activity`, passing the list of newly created `CodeEntity` nodes to the next stage of the system.
    *   **Rationale:** This decouples the real-time ingestion from the asynchronous enhancement process. The Orchestrator's job is done, and it has cleanly handed off the "hard problems" to the Dispatcher.

#### **iii. Orchestrator Boundaries**

The `Orchestrator`'s role is powerful but strictly limited to maintain its speed and simplicity.

*   **No Complex Queries:** Its Tier 1 resolver only performs highly optimized, direct lookups (e.g., via `find_code_entity_by_path`). All broad, graph-wide searches (like the `ENDS WITH` suffix match) are the exclusive responsibility of the asynchronous `GraphEnhancementEngine`.
*   **No LLM Calls:** The Orchestrator **never** calls a Large Language Model. This is a critical boundary to ensure the real-time ingestion path is always fast and deterministic.
*   **Single-File Focus:** Its logic is entirely focused on the single `FileProcessingRequest` it was given. It has no knowledge of "batches" or other files being processed concurrently, which makes it simple, stateless, and easy to test.

---

### **Component C: The Intelligent Dispatcher (`dispatcher.py`)**

#### **i. Core Philosophy: The "On-Demand Conductor"**

This component is the heart of our efficient, event-driven architecture. It replaces the naive "always-on background worker" model. It is a stateful but highly efficient singleton that triggers resource-intensive enhancement tasks **only when necessary**, ensuring the system is both powerful and cost-effective.

#### **ii. Finalized Dispatcher Workflow**

1.  **Listens for Activity:** Its `notify_ingestion_activity` method is its sole entry point, called by the `Orchestrator` after every successful file ingestion.
2.  **Immediate Repair:** Its first action upon notification is to trigger the fast `run_repair_worker` task. This immediately attempts to resolve any `AWAITING_TARGET` links that can be satisfied by the newly ingested code, enabling rapid self-healing.
3.  **Manages Quiescence:** It then starts or resets a per-repository `asyncio.sleep` timer. This is our elegant, in-memory solution for detecting when a "storm" of file updates for a specific repository has ended. If a new notification for the same repository arrives, the timer is cancelled and reset.
4.  **Dispatches Enhancement Cycle:** If a timer completes without being cancelled, the repository is deemed quiescent. The Dispatcher then triggers the `_run_full_enhancement_cycle`, which performs two critical actions in order:
    *   **Ensures Indexes:** It first `await`s `graph_utils.ensure_all_indexes()`. This is a cheap, idempotent check that guarantees the database schema is optimized for the heavy queries that are about to follow.
    *   **Runs Tasks:** It then uses `asyncio.gather` to run the Tier 2 and Tier 3 enhancement tasks from the `GraphEnhancementEngine` concurrently.
5.  **Handles Errors Gracefully:** It wraps the `gather` call in a `try/except` block. If an enhancement task fails with a non-recoverable error, it logs the failure and calls `graph_utils.mark_enhancement_failed` to update the repository's status in the graph. This prevents the system from getting stuck in a loop retrying a broken task and provides a clear signal for monitoring.

---

### **Component D: The `graph_enhancement_engine.py` Module**

#### **i. Core Philosophy: A Library of "Enhancement Tasks"**

This module does not contain long-running workers. It is a library of one-shot, stateless `async` functions that are called on-demand by the `Dispatcher`. Its guiding principle is our most important one: **Provable Truth**.

#### **ii. Finalized Task Responsibilities**

1.  **`run_tier2_enhancement` (The Heuristic Detective):**
    *   **Trigger:** Called by the `Dispatcher` for a quiescent repository.
    *   **Action:** It queries the graph for all `PendingLink`s with `status: 'READY_FOR_HEURISTICS'`. For each link, it runs a prioritized chain of deterministic queries: first, an exact match on `canonical_fqn`, and second, the verified suffix match.
    *   **Heuristic:** The suffix match uses a direct, performant Cypher query (`... WHERE n.canonical_fqn ENDS WITH '...'`) via `graph_utils`, leveraging the power of our chosen Neo4j backend.
    *   **Outcome:** If it finds **exactly one** unambiguous match, it creates the final `Relationship`. If it finds zero or multiple candidates, it promotes the link to `READY_FOR_LLM`, passing the candidates along as context.

2.  **`run_tier3_enhancement` (The LLM Consultant):**
    *   **Trigger:** Called by the `Dispatcher` for a quiescent repository.
    *   **Action:** It implements our **"Consult, Verify, Cache"** workflow. It queries for `READY_FOR_LLM` links, checks the `ResolutionCache`, constructs a rich prompt (including the source code and any candidates from Tier 2), and calls the LLM to get a *hint*—a suggested `canonical_fqn`.
    *   **Verification:** It **never** trusts the LLM blindly. It takes the LLM's suggested FQN and immediately runs a query to **verify** that a `CodeEntity` with that FQN actually exists in our graph.
    *   **Outcome:** If the hint is verified, it creates the link and populates the `ResolutionCache`. If not, it updates the `PendingLink` to `AWAITING_TARGET`.

3.  **`run_repair_worker` (The Self-Healer):**
    *   **Trigger:** Called by the `Dispatcher` immediately after every successful ingestion.
    *   **Action:** It checks if any of the newly created `CodeEntity`s satisfy an `AWAITING_TARGET` link by matching the `awaits_fqn` field.
    *   **Outcome:** If a match is found, it creates the final `Relationship`, completing the self-healing cycle and paying off the "debt" created by the LLM tier.

### **Component C: The Intelligent Dispatcher (`dispatcher.py`)**

#### **i. Core Philosophy: The "On-Demand Conductor"**

This component is the heart of our efficient, event-driven architecture. It replaces the naive and inefficient "always-on background worker" model. It is a stateful but highly efficient singleton that triggers resource-intensive enhancement tasks **only when necessary**, ensuring the system is both powerful and cost-effective.

#### **ii. Finalized Dispatcher Workflow**

1.  **Listens for Activity:** Its `notify_ingestion_activity` method is its sole entry point, called by the `Orchestrator` after every successful file ingestion.
2.  **Immediate Repair:** Its first action upon notification is to trigger the fast `run_repair_worker` task. This immediately attempts to resolve any `AWAITING_TARGET` links that can be satisfied by the newly ingested code, enabling rapid self-healing.
3.  **Manages Quiescence:** It then starts or resets a per-repository `asyncio.sleep` timer. This is our elegant, in-memory solution for detecting when a "storm" of file updates for a specific repository has ended.
4.  **Dispatches Enhancement Cycle:** If a timer completes without being cancelled, the repository is deemed quiescent. The Dispatcher then calls the `_run_full_enhancement_cycle`, which orchestrates the asynchronous work.
5.  **Handles Errors Gracefully:** It wraps the enhancement tasks in a `try/except` block. If a task fails with a non-recoverable error, it logs the failure and calls `graph_utils.mark_enhancement_failed` to update the repository's status in the graph, preventing futile retries.

---

### **Component D: The `graph_enhancement_engine.py` Module**

#### **i. Core Philosophy: A Library of "Enhancement Tasks"**

This module does not contain long-running workers. It is a library of one-shot, stateless `async` functions that are called on-demand by the `Dispatcher`. Its guiding principle is our most important one: **Provable Truth**.

#### **ii. Finalized Task Responsibilities**

1.  **`run_tier2_enhancement` (The Heuristic Detective):**
    *   **Trigger:** Called by the Dispatcher for a quiescent repository.
    *   **Action:** It queries for all `PendingLink`s with `status: 'READY_FOR_HEURISTICS'`. For each link, it runs a prioritized chain of deterministic queries: first, an exact match on `canonical_fqn`, and second, the verified suffix match.
    *   **Heuristic:** The suffix match uses a direct, performant Cypher query (`... WHERE n.canonical_fqn ENDS WITH '...'`) via `graph_utils`, leveraging the power of our chosen **Neo4j** backend.
    *   **Outcome:** If it finds **exactly one** unambiguous match, it creates the final `Relationship`. If it finds zero or multiple candidates, it promotes the link to `READY_FOR_LLM`.

2.  **`run_tier3_enhancement` (The LLM Consultant):**
    *   **Trigger:** Called by the Dispatcher for a quiescent repository.
    *   **Action:** It implements our **"Consult, Verify, Cache"** workflow. It queries for `READY_FOR_LLM` links, checks the `ResolutionCache`, constructs a rich prompt, and calls the LLM to get a *hint*—a suggested `canonical_fqn`.
    *   **Verification:** It **never** trusts the LLM blindly. It takes the LLM's suggested FQN and immediately runs a query to **verify** that a `CodeEntity` with that FQN actually exists in our graph.
    *   **Outcome:** If the hint is verified, it creates the link and populates the `ResolutionCache`. If not, it updates the `PendingLink` to `AWAITING_TARGET`.

3.  **`run_repair_worker` (The Self-Healer):**
    *   **Trigger:** Called by the `Dispatcher` immediately after every successful ingestion.
    *   **Action:** It checks if any of the newly created `CodeEntity`s satisfy an `AWAITING_TARGET` link by matching the `awaits_fqn` field.
    *   **Outcome:** If a match is found, it creates the final `Relationship`, completing the self-healing cycle.

---

### **Component E: The Infrastructure & Utility Layer**

These modules provide the foundational services that our core components rely on.

#### **i. `graph_utils.py` (The Neo4j Gateway)**

*   **Core Philosophy:** The **Data Access Layer (DAL)**. This module encapsulates all database interaction and is the only component that contains Neo4j-specific Cypher queries. It provides a clean, abstract API to the rest of the system.
*   **Key Responsibilities (Finalized):**
    1.  **Schema Management:** Provides the `ensure_all_indexes()` function, which is called on application startup to idempotently create all necessary simple and composite indexes in Neo4j.
    2.  **Atomic Operations:** Provides the `atomic_get_and_increment_local_save()` function, which uses an atomic `MERGE ... SET` Cypher query to prevent versioning race conditions.
    3.  **Direct Query Execution:** Provides the `execute_cypher_query()` function to run advanced queries (like our `ENDS WITH` heuristic) and correctly hydrate the results.
    4.  **Robustness:** All of its database-touching functions are hardened with a `tenacity`-based retry mechanism that is specifically configured to handle transient `neo4j` driver exceptions.

#### **ii. `cognee_adapter.py` (The Translator)**

*   **Core Philosophy:** A pure, stateless translator. Its sole job is to convert our internal Pydantic models (`CodeEntity`, `PendingLink`, etc.) into the specific `cognee.Node` and edge tuple formats required by `graph_utils.py`.
*   **Key Responsibility:** It must correctly populate the `attributes` dictionary of each `cognee.Node`, including the `index_fields` list that `graph_utils.ensure_all_indexes()` uses as its blueprint for managing the database schema.

#### **iii. `main.py` (The Application Entry Point)**

*   **Core Philosophy:** A simple, single-purpose startup script.
*   **Key Responsibilities:**
    1.  **Initialize Schema:** Its first action is to `await graph_utils.ensure_all_indexes()` to prepare the database.
    2.  **Run Application:** It then starts the main application loop (e.g., a web server or, in our case, a simple `asyncio` loop that keeps the process alive) so that the event-driven `Dispatcher` can receive notifications.

#### **iv. Other Utilities (`utils.py`, `configs.py`)**

*   **`utils.py`:** Contains shared, stateless helper functions (`read_file_content`, `resolve_import_path`, etc.) that have no dependencies on other system components.
*   **`configs.py`:** A centralized location for all system configuration values, such as `QUIESCENCE_PERIOD_SECONDS` and `GENERIC_CHUNK_SIZE`.

---














---

### Action Plan: From Blueprint to Working System**

**Overall Goal:** To build a robust, language-agnostic code analysis and graph ingestion pipeline that prioritizes provable truth and handles complex linking through a tiered, asynchronous engine.

This plan is divided into four main phases of work.

---

### **Phase 1: Solidify the Foundation (The Data Contracts & Core Utilities)**

**Objective:** To update the core data structures and utilities to match our final architecture. This is the bedrock upon which everything else is built.

**Action Items:**

1.  **Finalize `entities.py`:**
    *   **Task:** Replace the contents of `src/parser/entities.py` with the final, agreed-upon version.
    *   **Key Changes:** This introduces the crucial `RawSymbolReference`, `ReferenceContext`, `PendingLink`, and `ResolutionCache` models. It also adds the `import_id` and `root_namespace` fields to `FileProcessingRequest` and uses robust `Enums` for statuses and types.
    *   **Status:** The blueprint is complete. This is a copy-and-paste action.

2.  **Finalize `graph_utils.py`:**
    *   **Task:** Create or replace the contents of `src/parser/graph_utils.py` with the final version.
    *   **Key Changes:** This module will now be the *only* part of the parser library (besides the adapter) that imports from the `cognee` library. It will contain the new, generic functions like `find_nodes_with_filter` and `delete_nodes_with_filter`, as well as the new functions for `check_content_exists` and `update_heartbeat`.
    *   **Status:** The blueprint is complete. This is a copy-and-paste action.

3.  **Finalize `cognee_adapter.py`:**
    *   **Task:** Refactor `src/parser/cognee_adapter.py` to correctly translate our new set of entities (`PendingLink`, etc.) into the `cognee.Node` and edge tuple formats.
    *   **Key Changes:** It must now handle all `AdaptableNode` types and correctly import its `cognee` dependencies from their true source.
    *   **Status:** The blueprint is complete. This is a copy-and-paste action.

**Outcome of Phase 1:** The foundational data models and database interaction layer are stable, consistent, and ready to be used by the higher-level components.

---

### **Phase 2: Refactor the "Reporters" (The Parsers)**

**Objective:** To refactor all existing parsers to adhere to the "Sufficient Context Reporter" philosophy.

**Action Items:**

1.  **Refactor `CppParser`:**
    *   **Task:** Implement the V2, "single-pass, query-driven" version of `cpp_parser.py` that we designed.
    *   **Key Changes:**
        *   The `parse` method will be restructured to only `yield CodeEntity` and `RawSymbolReference`.
        *   All `yield Relationship` and `yield CallSiteReference` calls will be removed.
        *   Implement the `FileContext` class to build a file-local symbol table during the AST walk.
        *   Implement the `_resolve_context_for_reference` helper to use the `FileContext` to produce the richest possible `ReferenceContext` for each reference.
    *   **Status:** The full code blueprint is complete. This is a copy-and-paste and refinement action.

2.  **Refactor All Other Parsers (`PythonParser`, `JavascriptParser`, etc.):**
    *   **Task:** Apply the same architectural pattern to all other existing language parsers.
    *   **Key Changes:** Each parser must be modified to stop yielding `Relationship`s and instead yield `RawSymbolReference`s with a populated `ReferenceContext`. The intelligence for determining `import_type` (`RELATIVE` vs. `ABSOLUTE`) must be implemented within each parser, as it is a language-specific syntactic check.
    *   **Status:** This requires detailed engineering work for each language, but the *pattern* is now clearly defined by the `CppParser` example.

**Outcome of Phase 2:** All parsers now speak the same, universal language. They provide a standardized, high-quality stream of data for the Orchestrator to consume.

---

### **Phase 3: Implement the "Real-Time Engine" (The Orchestrator)**

**Objective:** To implement the Tier 1 resolver, which handles the fast, high-confidence parts of file ingestion.

**Action Items:**

1.  **Refactor `orchestrator.py`:**
    *   **Task:** Replace the existing `process_single_file` function with the final version we designed.
    *   **Key Changes:**
        *   The logic will be updated to handle the `is_delete` flag and idempotency checks correctly.
        *   It will consume `CodeEntity` and `RawSymbolReference` from the parser.
        *   It will contain the logic for finalizing `CodeEntity` IDs and creating structural relationships (`CONTAINS_CHUNK`, `DEFINES_CODE_ENTITY`).
        *   It will implement the **Tier 1 Resolver**, attempting to resolve only the most certain links (e.g., relative imports).
        *   For all other references, it will create `PendingLink` nodes.
        *   It will correctly manage the database transaction and ping the `IngestionHeartbeat` node upon completion.
    *   **Status:** The full code blueprint is complete. This is a copy-and-paste action.

**Outcome of Phase 3:** The core ingestion pipeline is functional. We can now process any file from any supported language, and the graph will be populated with all defined entities, all structural relationships, all high-confidence semantic links, and a clear "to-do" list of `PendingLink` debts.

---

### **Phase 4: Implement the "Asynchronous Engine" (The Linking Workers)**

**Objective:** To build the background workers that provide the system's "eventual consistency" and advanced linking capabilities.

**Action Items:**

1.  **Create `linking_engine.py`:**
    *   **Task:** Create a new file, `src/parser/linking_engine.py`.
    *   **Status:** This is a new implementation, but the logic is fully designed.

2.  **Implement the "Janitor" Worker (Quiescence Trigger):**
    *   **Task:** Write the `run_janitor_worker` function within the new file.
    *   **Key Changes:** This function will run in a loop, query for active `IngestionHeartbeat` nodes, check their timestamps against a `QUIESCENCE_PERIOD`, and promote `PendingLink`s to the `READY_FOR_HEURISTICS` status.
    *   **Status:** The blueprint and pseudo-code are complete. This is a straightforward implementation task.

3.  **Implement the "Heuristic Resolver" Worker (Tier 2):**
    *   **Task:** Write the worker function that polls for `PendingLink`s in the `READY_FOR_HEURISTICS` state.
    *   **Key Changes:** It will implement the prioritized chain of deterministic, graph-wide queries (checking `import_id`, then exact `canonical_fqn`). It will create the final `Relationship` on an unambiguous success or promote the link to `READY_FOR_LLM` on failure or ambiguity.
    *   **Status:** The logic and query patterns are fully designed. This is a straightforward implementation task.

4.  **Implement the "LLM Resolver" Worker (Tier 3):**
    *   **Task:** Write the optional worker function that polls for `PendingLink`s in the `READY_FOR_LLM` state.
    *   **Key Changes:** It will implement the full lifecycle: check `ResolutionCache`, construct the batched prompt, call the `cognee.llm` interface, verify the LLM's response against the graph, and create the final `Relationship` and `ResolutionCache` nodes.
    *   **Status:** The logic, prompt structure, and workflow are fully designed. This is a straightforward implementation task.

---












---

### **File Change Plan: `orchestrator.py`**

**Current State:** A mix of old logic (direct entity creation, old `FileProcessingAction` ideas) and incomplete new logic.
**Goal State:** A lean, robust, Tier 1 resolver that perfectly implements the "Speed, Safety, and Honesty" philosophy.

---

#### **Action Item 1: Clean Up Imports**

The first step is to align the imports with our final `entities.py` contract and the new `graph_utils.py` API.

*   **REMOVE:** `FileProcessingAction`, `CallSiteReference`, `OrchestratorOutput`. These are obsolete.
*   **ADD:** `PendingLink`, `LinkStatus`, `ImportType`, `ReferenceContext`. These are the new, core data models for our linking engine.
*   **CHANGE Graph Util Imports:** We need to update the `graph_utils` imports to match the new, more granular functions we designed. Specifically, we will no longer use a simple `delete_all_versions_of_file`, but a more generic `delete_nodes_with_filter`.

**Code Context (`orchestrator.py` - Top of file):**
```python
# --- BEFORE ---
from .entities import (
    FileProcessingRequest, FileProcessingAction, # <-- WRONG
    Repository, SourceFile, TextChunk, CodeEntity, Relationship,
    CallSiteReference, ParserOutput, OrchestratorOutput # <-- WRONG
)
from .graph_utils import (
    delete_all_versions_of_file, get_latest_local_save_count, # <-- WRONG
    save_graph_data, check_content_exists, find_code_entity_by_path,
    update_heartbeat
)
# ...

# --- AFTER (The New Plan) ---
import asyncio
import inspect
# ... (other standard imports) ...
import hashlib # For idempotency check
import os # For path manipulation

# --- All our final data contracts ---
from .entities import (
    FileProcessingRequest, Repository, SourceFile, TextChunk,
    CodeEntity, RawSymbolReference, ParserOutput, Relationship,
    PendingLink, LinkStatus, ImportType, ReferenceContext
)
from .parsers.base_parser import BaseParser
from .chunking import generate_text_chunks_from_slice_lines
from .utils import logger, read_file_content, parse_temp_code_entity_id
# --- The full set of required graph utilities ---
from .graph_utils import (
    delete_nodes_with_filter, get_latest_local_save_count,
    save_graph_data, check_content_exists, find_code_entity_by_path,
    update_heartbeat
)
from .cognee_adapter import adapt_parser_entities_to_graph_elements
from cognee.infrastructure.databases.graph import get_graph_db
```

---

#### **Action Item 2: Refactor the `process_single_file` function**

This is the main body of work. We will restructure the function to follow our step-by-step mandate precisely.

**1. Simplify the Entry Point and `DELETE` Logic:**
*   **The Problem:** The old code had `tx.commit()` calls inside the `if` blocks, which is not ideal when using a `with` statement for transactions.
*   **The Change:** We will simplify this. The `with` block will handle commits and rollbacks automatically. The `DELETE` action becomes a clean, early exit.

**2. Implement Idempotency and Correct Versioning:**
*   **The Problem:** The old code had a simple "delete then add" strategy. This is not true versioning. The new logic must check for existing content and correctly calculate the new version string.
*   **The Change:** We will insert the `content_hash` check and the call to `get_latest_local_save_count` at the beginning of the `UPSERT` path.

**3. Implement the Full "Phase A" Assembly Logic:**
*   **The Problem:** The old `_orchestrate_single_file_upsert` function had placeholder logic for finalizing IDs (`final_ce_id = "..."`). This needs to be a real implementation.
*   **The Change:** We will build the `temp_id_to_final_id_map` by looping through the `CodeEntity` objects reported by the parser and using their `@line` number to find their parent `TextChunk`. This is a crucial step that was previously missing.

**4. Implement the "Tier 1 Resolver" and "Debt Creation":**
*   **The Problem:** This logic was completely absent.
*   **The Change:** We will add a new loop that iterates through the `RawSymbolReference`s. It will call our `_resolve_tier1_link` helper. Based on the result, it will either create a final `Relationship` object or a `PendingLink` debt object. This is the heart of the new "honest" resolver.

**Code Context (The new `process_single_file` function):**
```python
# This is the full, final implementation for the orchestrator

async def process_single_file(request: FileProcessingRequest):
    """
    Main library entry point. Manages the atomic transaction for a single file request.
    This is the Tier 1, real-time part of the engine.
    """
    log_prefix = f"ORCHESTRATOR ({request.repo_id}@{request.branch}|{Path(request.absolute_path).name})"
    db = get_graph_db()
    session = None

    try:
        session = db.session()
        # The 'with' block ensures tx.commit() on success or tx.rollback() on error.
        with session.begin_transaction() as tx:
            repo_id_with_branch = f"{request.repo_id}@{request.branch}"
            relative_path = str(Path(request.absolute_path).relative_to(request.repo_path))

            # 1. HANDLE DELETE and EMPTY FILE SCENARIOS
            content = await read_file_content(str(request.absolute_path))
            if request.is_delete or not content or not content.strip():
                delete_filter = {"repo_id_str": repo_id_with_branch, "relative_path_str": relative_path}
                await delete_nodes_with_filter(tx, delete_filter)
                logger.info(f"{log_prefix}: Completed DELETE or empty file action for '{relative_path}'.")
                return

            # 2. VERSIONING & IDEMPOTENCY
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            if await check_content_exists(tx, content_hash):
                logger.info(f"{log_prefix}: Content hash exists. Skipping file.")
                return

            latest_save_count = await get_latest_local_save_count(tx, repo_id_with_branch, relative_path, request.commit_index)
            version_id = f"{request.commit_index}-{str(latest_save_count + 1).zfill(3)}"
            source_file_id = f"{repo_id_with_branch}|{relative_path}|{version_id}"

            # Since this is a new version, we still clear out any old versions for this path
            await delete_nodes_with_filter(tx, {"repo_id_str": repo_id_with_branch, "relative_path_str": relative_path})

            # 3. PARSE & COLLECT
            parser = _get_parser_for_file(Path(request.absolute_path))
            if not parser:
                logger.error(f"{log_prefix}: No parser found. Aborting.")
                return

            parser_yields = [item async for item in parser.parse(source_file_id, content)]
            slice_lines = next((item for item in parser_yields if isinstance(item, list)), [])
            code_entities = [item for item in parser_yields if isinstance(item, CodeEntity)]
            raw_references = [item for item in parser_yields if isinstance(item, RawSymbolReference)]

            # 4. ASSEMBLE FILE'S "ISLAND" (Phase A)
            entities_to_save: List[Union[Repository, SourceFile, TextChunk, CodeEntity, Relationship, PendingLink]] = []

            repo_node = Repository(id=repo_id_with_branch, path=request.repo_path, import_id=request.import_id)
            entities_to_save.append(repo_node)
            entities_to_save.append(SourceFile(id=source_file_id, content_hash=content_hash))

            final_text_chunks = generate_text_chunks_from_slice_lines(source_file_id, content, slice_lines)
            entities_to_save.extend(final_text_chunks)
            for chunk in final_text_chunks:
                entities_to_save.append(Relationship(source_id=source_file_id, target_id=chunk.id, type="CONTAINS_CHUNK"))

            temp_id_to_final_id_map: Dict[str, str] = {}
            for temp_ce in code_entities:
                parsed_id = parse_temp_code_entity_id(temp_ce.id)
                if not parsed_id: continue
                fqn_part, start_line_0 = parsed_id
                parent_chunk = next((c for c in final_text_chunks if c.start_line <= (start_line_0 + 1) <= c.end_line), None)
                if not parent_chunk:
                    logger.warning(f"{log_prefix}: Could not find parent chunk for entity '{temp_ce.id}'.")
                    continue

                final_ce_id = f"{parent_chunk.id}|{fqn_part}"
                temp_id_to_final_id_map[temp_ce.id] = final_ce_id
                entities_to_save.append(CodeEntity(id=final_ce_id, type=temp_ce.type, snippet_content=temp_ce.snippet_content))
                entities_to_save.append(Relationship(source_id=parent_chunk.id, target_id=final_ce_id, type="DEFINES_CODE_ENTITY"))

            # 5. TIER 1 RESOLUTION & PENDING LINK CREATION
            for ref in raw_references:
                final_source_id = temp_id_to_final_id_map.get(ref.source_entity_id, ref.source_entity_id)

                resolved_target_id = await _resolve_tier1_link(tx, ref, request)
                if resolved_target_id:
                    entities_to_save.append(Relationship(source_id=final_source_id, target_id=resolved_target_id, type=ref.reference_type))
                else:
                    question_str = f"{final_source_id}|{ref.target_expression}|{ref.reference_type}"
                    pending_link_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, question_str))
                    entities_to_save.append(PendingLink(id=pending_link_id, reference_data=ref))

            # 6. ADAPT & SAVE ALL NEW DATA
            nodes_to_add, edges_to_add = adapt_parser_entities_to_graph_elements(entities_to_save)
            await save_graph_data(tx, nodes_to_add, edges_to_add)

            # 7. UPDATE HEARTBEAT for the quiescence trigger
            await update_heartbeat(tx, repo_id_with_branch)

    except Exception as e:
        logger.error(f"{log_prefix}: Transaction failed. Error: {e}", exc_info=True)
        # The 'with' block handles rollback automatically
    finally:
        if session:
            session.close()
```

---

#### **iii. What The New Orchestrator DOES NOT DO**

This section is just as important for the next developer/AI.
*   **It does NOT perform complex, graph-wide queries.** The `_resolve_tier1_link` helper only handles the simplest case (relative path imports). All other `RawSymbolReference`s are turned into `PendingLink`s.
*   **It does NOT call the LLM.**
*   **It does NOT know about "batches" of files.** It is a pure, stateless function for a single file.

---









---

### **File Change Plan: `cpp_parser.py`**

**Current State:** A blueprint with placeholder logic for FQN generation and context resolution.
**Goal State:** A complete, robust, single-pass parser that uses a file-local symbol table to generate high-quality `CodeEntity` and `RawSymbolReference` objects.

---

#### **Action Item 1: Enhance the `FileContext`**

The `FileContext` is the in-memory brain for a single parse run. It needs to be more sophisticated to track the information required for V2-level context resolution.

*   **The Problem:** The current `FileContext` is too simple. It doesn't track variable types or properly handle nested scopes for `using` directives.
*   **The Change:** We will enhance its structure to be a more complete symbol table.

**Code Context (`FileContext` class):**
```python
# --- BEFORE ---
class FileContext:
    def __init__(self, source_file_id: str):
        self.source_file_id = source_file_id
        self.scope_stack: List[str] = []
        self.includes: Dict[str, str] = {}
        self.active_usings: Dict[int, List[str]] = {}
        self.local_definitions: Dict[str, str] = {}

# --- AFTER (The New Plan) ---
class FileContext:
    """A stateful object to hold all context during a single file parse."""
    def __init__(self, source_file_id: str):
        self.source_file_id = source_file_id
        self.scope_stack: List[str] = []
        # Maps an include path to its type ('system' or 'quoted')
        self.include_map: Dict[str, str] = {}
        # Maps a scope's unique ID (the node.id) to a list of active 'using' namespaces
        self.active_usings: Dict[int, List[str]] = {}
        # Maps a simple name (alias or symbol) to the full path it was imported from
        self.import_map: Dict[str, str] = {}
        # Maps a full FQN to its temporary ID (FQN@line)
        self.local_definitions: Dict[str, str] = {}
        # A map of (scope_node_id, var_name) -> type_name
        self.local_variable_types: Dict[Tuple[int, str], str] = {}
```

---

#### **Action Item 2: Fully Implement the Helper Methods**

This is the most critical part. We will replace the placeholder logic with the full, sophisticated implementations from your original parser, adapted for the new V2 architecture.

**1. Fully Implement `_get_node_name_text` and `_get_fqn_for_node`:**
*   **The Problem:** These were left as placeholders (`pass` or simplified logic).
*   **The Change:** We will integrate the **full, complex logic** from your original `cpp_parser.py` file for these two functions. They are excellent, battle-tested heuristics for extracting names and parameters, and they represent the core of the parser's "expertise." The only change to `_get_fqn_for_node` is that it will now receive the `scope_stack` from the `FileContext` instead of calculating it by walking up the tree itself.

**2. Fully Implement `_resolve_context_for_reference`:**
*   **The Problem:** This was a naive placeholder. It needs to implement the full, prioritized lookup chain.
*   **The Change:** This function will now be the "intelligent" part of the parser. It will perform a series of checks against the `FileContext` to determine the best possible `ReferenceContext`.

**Code Context (The new resolver logic):**
```python
def _resolve_context_for_reference(self, target_expr: str, node: TSNODE_TYPE, context: FileContext) -> ReferenceContext:
    """The V2 resolver. Uses the file-local context to determine the best possible context."""

    # Attempt 1: Is this an object method call (e.g., my_obj.do_work())?
    if '.' in target_expr or '->' in target_expr:
        # A real implementation would parse the expression to find the object name
        # and then look up its type in context.local_variable_types.
        # This provides the highest-quality context for method calls.
        pass # Placeholder for this advanced logic

    # Attempt 2: Does the symbol match a known import?
    base_symbol = target_expr.split('::')[0]
    if base_symbol in context.import_map:
        include_path = context.import_map[base_symbol]
        include_type = context.include_map.get(include_path, "quoted") # Default to quoted/relative
        return ReferenceContext(
            import_type=ImportType.ABSOLUTE if include_type == 'system' else ImportType.RELATIVE,
            path_parts=[include_path]
        )

    # Attempt 3: Can we resolve it by prepending active `using` namespaces?
    # Logic to walk up the scope from `node`, get the active namespaces from
    # context.active_usings, and check if `using_ns::target_expr` exists
    # in context.local_definitions.

    # Fallback: Treat as a global/absolute reference.
    return ReferenceContext(import_type=ImportType.ABSOLUTE, path_parts=target_expr.split("::"))
```

---

#### **Action Item 3: Implement the Single-Pass AST Walk**

The `parse` method will be restructured to use a single, recursive walk function.

*   **The Problem:** The previous blueprint was still structured as multiple loops.
*   **The Change:** We will implement the `_walk_and_process` function. Its job is to traverse every node. As it enters and exits scope-defining nodes (like namespaces and classes), it will **update the `FileContext.scope_stack`**. For every node it visits, it will check if it's a "point of interest" (a definition or reference found by our pre-run queries) and process it using the *current* state of the `FileContext`.

**Code Context (The new `parse` and `_walk_and_process` methods):**
```python
async def parse(self, source_file_id: str, file_content: str) -> AsyncGenerator[ParserOutput, None]:
    # ... setup logic to get root_node ...

    # STEP 1: Pre-computation - Run all queries once to find nodes of interest
    interest_nodes = {} # Maps node_id -> list of (interest_type, capture_name)
    for query_name, query in self.queries.items():
        interest_type = "definition" if "definition" in query_name else "reference"
        for match, capture_name in query.matches(root_node):
            # ... populate interest_nodes dictionary ...

    # STEP 2: The Single, Context-Building Walk
    file_context = FileContext(source_file_id)

    # Pre-populate includes and usings to provide context for the main walk
    # ... logic to run 'includes' and 'using_namespace' queries and populate file_context ...

    # Kick off the recursive walk that will yield all entities and references
    async for item in self._walk_and_process(root_node, file_context, content_bytes, interest_nodes):
        yield item

async def _walk_and_process(self, node, context, ...):
    # ... update context.scope_stack on entry ...

    if node.id in interest_nodes:
        # ... process the node as a definition or reference ...
        # ... using the CURRENT context.scope_stack and context.active_usings ...
        # ... yield CodeEntity or RawSymbolReference ...

    for child in node.children:
        async for item in self._walk_and_process(child, context, ...):
            yield item

    # ... update context.scope_stack on exit ...
```

---


















---

### **File Change Plan: `graph_utils.py`**

**Current State:** A good set of generic helper functions for interacting with the `cognee` graph adapter.
**Goal State:** A complete, production-ready toolkit that provides every specific query and mutation operation required by the V2 Orchestrator and the Asynchronous Linking Engine.

**The Core Philosophy:** This module is the **Data Access Layer (DAL)**. It is the only place in our library (besides the adapter) that knows how to talk to the `cognee` graph engine. It must provide a clean, intention-revealing API to the rest of the system.

---

#### **Action Item 1: Refactor Imports and Correct Data Types**

The current code has some import errors and uses incorrect type hints based on our final, proven `cognee` API.

*   **The Problem:** It imports `DataPoint`, `CogneeEdgeTuple`, etc., from `.entities`, which is wrong. It also refers to `Node` when the adapter functions expect `DataPoint`. The function signatures for saving data are incorrect.
*   **The Change:** We must correct all imports to point to the canonical `cognee` library paths and ensure all function signatures use the correct types (`DataPoint` for nodes, and a specific tuple format for edges).

**Code Context (`graph_utils.py` - Top of file):**
```python
# --- BEFORE ---
from .entities import DataPoint, PendingLink, Relationship, CogneeEdgeTuple, LinkStatus
from cognee.infrastructure.engine.models.DataPoint import DataPoint, MetaData # Incorrect Path

# --- AFTER (The New Plan) ---
import asyncio
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone

from .utils import logger
from .entities import PendingLink, LinkStatus

# --- Correct, Proven Cognee Imports ---
from cognee.infrastructure.engine.models.DataPoint import DataPoint, MetaData
from cognee.modules.graph.graph_objects import CogneeEdgeTuple
from cognee.infrastructure.databases.graph.get_graph_engine import get_graph_engine
# ... (all other cognee.* imports)
```

---

#### **Action Item 2: Implement a Robust `get_adapter` Singleton**

*   **The Problem:** The current `get_adapter` uses a global variable, which can be problematic in complex asynchronous applications and for testing.
*   **The Change:** We will implement this as a more robust, standard singleton pattern to ensure we only initialize the graph engine once.

**Code Context (`graph_utils.py`):**
```python
# This is a more standard and testable way to handle a singleton.
_graph_adapter_instance = None

async def get_adapter():
    """A robust singleton accessor for the graph engine adapter."""
    global _graph_adapter_instance
    if _graph_adapter_instance is None:
        logger.info("GRAPH_UTILS: Initializing graph engine adapter...")
        _graph_adapter_instance = await get_graph_engine()
        logger.info("GRAPH_UTILS: Graph engine adapter initialized.")
    return _graph_adapter_instance
```

---

#### **Action Item 3: Implement All Required Functions**

The Orchestrator and Linking Engine blueprints require several specific functions that are missing or incomplete. We must fully implement them.

*   **`get_latest_local_save_count`:**
    *   **The Problem:** The current version queries all versions and filters in Python. We've learned from the `cognee` expert that `get_filtered_graph_data` does not support `STARTS_WITH`.
    *   **The Decision:** Our existing implementation is actually the **correct and necessary** one. The blueprint for this function is sound. We will keep it, but add more detailed logging.

*   **`check_content_exists`:**
    *   **The Problem:** This function was missing from your file.
    *   **The Change:** We need to implement it fully. It will perform a direct filter query for the `content_hash`.

*   **`find_code_entity_by_path`:**
    *   **The Problem:** This was a placeholder. This is a critical function for our Tier 1 resolver.
    *   **The Change:** We must implement the two-step query logic we designed: first find the latest version of the `SourceFile` by its path, then search for a `CodeEntity` descendant with a matching FQN. This will require storing `repo_id_str`, `relative_path_str`, and `fqn` in the metadata of the respective nodes so they can be queried.

*   **`find_pending_links` and `update_pending_link_status`:**
    *   **The Problem:** These were missing. They are essential for the Janitor and other workers.
    *   **The Change:** We will implement them as simple, filtered queries that find `PendingLink` nodes by their `status` and update them.

**The Final `graph_utils.py` File Plan:**
The resulting file will be a complete DAL, containing all the functions listed in the previous response, with corrected imports, robust logic, and detailed logging.

---

### **File Change Plan: `utils.py`**

**Current State:** A very solid collection of stateless helper functions.
**Goal State:** The same, but with the addition of one or two more helpers to support the new architecture and a cleanup of unused functions.

---

#### **Action Item 1: Add a Path Resolution Utility**

*   **The Problem:** The Orchestrator's Tier 1 resolver needs to reliably resolve a relative import path (e.g., `"../../common/helpers.h"`) from a source file's path to a canonical, repository-root-based path. This logic should not live in the Orchestrator.
*   **The Change:** We will add a new, pure function to `utils.py` to handle this.

**Code Context (A new function in `utils.py`):**
```python
import os
from pathlib import Path

def resolve_import_path(source_file_rel_path: str, import_rel_path: str) -> Optional[str]:
    """
    Resolves a relative import path against the path of the source file.
    Returns a canonical, repository-root-based path.
    e.g., ('src/app/main.py', '../services/api.py') -> 'src/services/api.py'
    """
    try:
        source_dir = Path(source_file_rel_path).parent
        # os.path.normpath handles '..' and '.' correctly.
        resolved_path = os.path.normpath(os.path.join(source_dir, import_rel_path))
        return resolved_path
    except Exception:
        return None
```

---

#### **Action Item 2: Review and Clean Up**

*   **The Problem:** As the architecture has evolved, some functions in `utils.py` may no longer be necessary. For instance, `parse_temp_code_entity_id` is now less critical because the final ID construction is handled entirely within the Orchestrator.
*   **The Change:** We will perform a review of `utils.py` to ensure every function is still needed. We will keep generic, high-value helpers like `get_node_text` and `format_node_for_debug` and consider deprecating anything that was specific to an older design.

**The Final `utils.py` File Plan:**
The file will remain a lean, robust toolbox of generic, stateless helpers, with the addition of the crucial `resolve_import_path` function. It will have no dependencies on any other part of our system except for `tree-sitter`.
















---

### **File Change Plan: `cognee_adapter.py`**

**Current State:** A functional adapter that translates a list of our Pydantic models into `cognee.Node` objects and edge tuples. It's a good starting point.
**Goal State:** A more robust and intelligent adapter that correctly handles all of our new `entities`, including `PendingLink` and `ResolutionCache`, and more intelligently populates the node `attributes` for optimal querying by the `graph_utils` module.

**The Core Philosophy:** The adapter is the **"Shipping Department."** It is the final, stateless transformation step before data is handed off to the graph database. Its job is to be an expert on the `cognee.Node` data structure and to ensure that the data we've gathered is packaged perfectly for storage and later retrieval.

---

#### **Action Item 1: Correct Imports and Type Hinting**

*   **The Problem:** Your current adapter has a mix of correct and incorrect imports based on our latest findings. It also uses a generic `AdaptableNode` hint that isn't fully defined yet.
*   **The Change:** We will correct all imports to their final, proven paths and define the `AdaptableNode` union type directly in `entities.py` for clarity and reuse. We will also ensure the `CogneeEdgeTuple` matches the exact format required by the `graph_utils.save_graph_data` function.

**Code Context (`cognee_adapter.py` - Top of file):**
```python
# --- BEFORE ---
from .entities import Relationship, AdaptableNode
from cognee.modules.graph.cognee_graph.CogneeGraphElements import Node
CogneeEdgeTuple = Tuple[str, str, str, Dict[str, Any]]

# --- AFTER (The New Plan) ---
from typing import List, Dict, Any, Union, Tuple
import uuid

from .utils import logger
# Import the full, final set of models it needs to translate
from .entities import (
    Repository, SourceFile, TextChunk, CodeEntity, Relationship,
    PendingLink, ResolutionCache, AdaptableNode
)

# Import the proven, correct Cognee models
from cognee.modules.graph.cognee_graph.CogneeGraphElements import Node, Edge
```
*(Note: We will define `AdaptableNode` in `entities.py` as `Union[Repository, SourceFile, TextChunk, CodeEntity, PendingLink, ResolutionCache]`)*

---

#### **Action Item 2: Implement Intelligent Metadata and Indexing**

*   **The Problem:** The current adapter dumps all Pydantic model fields into the `attributes` dictionary. This is inefficient and doesn't explicitly define the `index_fields` that `graph_utils` will rely on for fast queries.
*   **The Change:** We will implement a more intelligent attribute population logic. It will still store all the data, but it will also create a specific `index_fields` list within the attributes, based on the node type. This makes the adapter an active participant in ensuring the graph is performant.

**Code Context (The main `adapt_parser_entities_to_graph_elements` function):**
```python
# This is the new, more intelligent logic inside the main for loop.
for p_node in p_nodes:
    p_slug_id = p_node.id

    # The attributes dictionary will be the full model dump for complete data preservation
    attributes = p_node.model_dump()
    attributes["node_type"] = p_node.type
    attributes["slug_id"] = p_slug_id # Keep the human-readable ID for debugging

    # --- NEW: Intelligent Indexing ---
    # Define which fields are critical for fast lookups by our graph_utils
    index_fields = ["slug_id", "node_type"]
    if isinstance(p_node, SourceFile):
        index_fields.extend(["repo_id_str", "relative_path_str", "content_hash"])
    elif isinstance(p_node, Repository):
        index_fields.append("provides_import_id")
    elif isinstance(p_node, PendingLink):
        index_fields.extend(["status", "awaits_fqn"])
    elif isinstance(p_node, CodeEntity):
        index_fields.append("canonical_fqn")

    attributes["index_fields"] = sorted(list(set(index_fields)))

    cognee_node_instance = Node(
        node_id=p_slug_id,
        attributes=attributes
    )
    cognee_nodes.append(cognee_node_instance)
```
*   **Rationale:** This change is critical. It makes the adapter responsible for telling the graph engine *how* to store the data for optimal performance. The `graph_utils` functions can now rely on these `index_fields` existing.

---

#### **Action Item 3: Improve Edge Creation Logic**

*   **The Problem:** The current logic `if p_rel.source_id in slug_id_set ...` is correct, but it assumes the `target_id` is also a node being created in the same batch. This is not always true for the final `Relationship`s created by the linking engine.
*   **The Change:** We will remove this check. The responsibility for providing valid `source_id` and `target_id`s now lies entirely with the **Orchestrator** and **Linking Engine**. The adapter becomes a "dumber," more stateless translator, which is good. It will simply attempt to create any edge it is given. The graph database will be responsible for raising an error if an ID doesn't exist.

**The Final `cognee_adapter.py` File Plan:**
The resulting file will be a lean, efficient, and robust translator. Its sole job is to convert our internal Pydantic models into the specific `cognee.Node` objects and edge tuples required by the `graph_utils` layer, correctly populating the `attributes` and defining the necessary `index_fields` for performance.

---

### **File Change Plan: `chunking.py`**

**Current State:** A robust, pure function that correctly chunks file content based on a list of slice lines.
**Goal State:** The same.

**The Core Philosophy:** This module is a **Pure Utility**. It takes data in, transforms it, and returns data. It has no side effects, no knowledge of the graph, and no dependencies on any other part of the system except for the `TextChunk` entity and the logger.

---

#### **Action Item: No Changes Needed**

Your current implementation of `generate_text_chunks_from_slice_lines` is excellent.
*   It correctly handles empty inputs.
*   It correctly handles out-of-bounds slice lines by creating a single chunk for the whole file.
*   It correctly handles duplicate and unsorted slice lines.
*   Its logging is clear and contextual.
*   The ID generation logic (`f"{source_file_id}|{chunk_index}@{start_line_1}-{end_line_1}"`) is exactly what the Orchestrator's ID finalization logic expects.

**Decision:** The `chunking.py` file is considered **complete and correct** for our V1 architecture. No changes are required. This is a perfect example of a well-designed, decoupled component.

---
















---

### **File Change Plan: `cpp_parser.py`**

**Current State:** A V2 blueprint with a single-pass structure but with simplified, placeholder logic in its core helper methods.
**Goal State:** A complete, robust, single-pass parser that uses a fully implemented file-local symbol table to generate high-quality `CodeEntity` and `RawSymbolReference` objects.

---

#### **Action Item 1: Enhance the `FileContext` Class**

The `FileContext` is the in-memory brain for a single parse run. It needs to be more sophisticated to track the information required for V2-level context resolution.

*   **The Problem:** The current `FileContext` is too simple. It doesn't track variable types or properly handle nested scopes for `using` directives.
*   **The Change:** We will enhance its structure to be a more complete symbol table.

**Code Context (`FileContext` class):**
```python
# --- BEFORE ---
class FileContext:
    def __init__(self, source_file_id: str):
        self.source_file_id = source_file_id
        self.scope_stack: List[str] = []
        self.include_map: Dict[str, str] = {}
        self.active_usings: Dict[int, List[str]] = {}
        self.local_definitions: Dict[str, str] = {}

# --- AFTER (The New Plan) ---
class FileContext:
    """A stateful object to hold all context during a single file parse."""
    def __init__(self, source_file_id: str):
        self.source_file_id = source_file_id
        self.scope_stack: List[str] = []
        # Maps an include path to its type ('system' or 'quoted')
        self.include_map: Dict[str, str] = {}
        # Maps a scope's unique ID (the node.id) to a list of active 'using' namespaces
        self.active_usings: Dict[int, List[str]] = {}
        # Maps a simple name (alias or symbol) to the full path it was imported from
        self.import_map: Dict[str, str] = {}
        # Maps a full FQN to its temporary ID (FQN@line)
        self.local_definitions: Dict[str, str] = {}
        # A map of (scope_node_id, var_name) -> type_name
        self.local_variable_types: Dict[Tuple[int, str], str] = {}
```

---

#### **Action Item 2: Fully Implement the Helper Methods**

This is the most critical part. We will replace the placeholder logic with full, sophisticated implementations.

**1. Fully Implement `_get_node_name_text` and `_get_fqn_for_node`:**
*   **The Problem:** These were left as placeholders in the last blueprint.
*   **The Change:** We will integrate the **full, complex logic** from your original `cpp_parser.py` file for these two functions. They are excellent, battle-tested heuristics for extracting names and parameters. The only change to `_get_fqn_for_node` is that it will now receive the `scope_stack` from the `FileContext` instead of calculating it by walking up the tree itself.

**2. Fully Implement `_resolve_context_for_reference`:**
*   **The Problem:** This was a naive placeholder. It needs to implement the full, prioritized lookup chain.
*   **The Change:** This function will now be the "intelligent" part of the parser. It will perform a series of checks against the `FileContext` to determine the best possible `ReferenceContext`.

**Code Context (The new resolver logic):**
```python
def _resolve_context_for_reference(self, target_expr: str, node: TSNODE_TYPE, context: FileContext) -> ReferenceContext:
    """The V2 resolver. Uses the file-local context to determine the best possible context."""

    # Attempt 1: Is this an object method call (e.g., my_obj.do_work())?
    if '.' in target_expr or '->' in target_expr:
        # A real implementation would parse the expression to find the object name
        # and then look up its type in context.local_variable_types.
        # This provides the highest-quality context for method calls.
        # This logic needs to be built out.
        pass

    # Attempt 2: Does the symbol match a known import?
    base_symbol = target_expr.split('::')[0]
    if base_symbol in context.import_map:
        include_path = context.import_map[base_symbol]
        include_type = context.include_map.get(include_path, "quoted") # Default to quoted/relative
        return ReferenceContext(
            import_type=ImportType.ABSOLUTE if include_type == 'system' else ImportType.RELATIVE,
            path_parts=[include_path] # Simplified, should be proper parts
        )

    # Attempt 3: Can we resolve it by prepending active `using` namespaces?
    # This requires walking up the AST from `node` to find its parent scope,
    # looking up that scope's ID in context.active_usings, and then checking
    # if `using_ns::target_expr` exists in context.local_definitions.

    # Fallback: Treat as a global/absolute reference.
    return ReferenceContext(import_type=ImportType.ABSOLUTE, path_parts=target_expr.split("::"))
```

---

#### **Action Item 3: Implement the Single-Pass AST Walk (`_walk_and_process`)**

The `parse` method will be restructured to use a single, recursive walk function.

*   **The Problem:** The previous blueprint was still structured as multiple loops. The `_walk_and_process` was a placeholder.
*   **The Change:** We will implement the `_walk_and_process` function fully. Its job is to traverse every node. As it enters and exits scope-defining nodes (like namespaces and classes), it will **update the `FileContext.scope_stack`**. For every node it visits, it will check if it's a "point of interest" (a definition or reference found by our pre-run queries) and process it using the *current* state of the `FileContext`.

**Code Context (The new `parse` and `_walk_and_process` methods):**
```python
async def parse(self, source_file_id: str, file_content: str) -> AsyncGenerator[ParserOutput, None]:
    # ... setup logic to get root_node ...

    # STEP 1: Pre-computation - Run all queries once to find nodes of interest
    interest_nodes: Dict[int, List[Tuple[str, str]]] = {}
    for query_name, query in self.queries.items():
        # ... logic to run query and populate interest_nodes dictionary ...
        # e.g., interest_nodes[node.id] = [("definition", "classes"), ...]

    # STEP 2: The Single, Context-Building Walk
    file_context = FileContext(source_file_id)

    # Pre-populate includes and usings to provide context for the main walk
    # ... logic to run 'includes' and 'using_namespace' queries and populate file_context ...

    # Kick off the recursive walk that will yield all entities and references
    async for item in self._walk_and_process(root_node, file_context, content_bytes, interest_nodes):
        yield item

async def _walk_and_process(self, node, context, content_bytes, interest_nodes):
    # --- Update Context on Entry ---
    # ... logic to update context.scope_stack if node is a scope ...
    # ... logic to update context.active_usings if node is a `using` directive ...
    # ... logic to update context.local_variable_types if node is a variable declaration ...

    # --- Process Node if it is a Point of Interest ---
    if node.id in interest_nodes:
        # For each match type on this node...
        for interest_type, capture_name in interest_nodes[node.id]:
            if interest_type == "definition":
                # Create and yield a CodeEntity, using the current scope_stack for the FQN
                # and add the definition to context.local_definitions
                # ...
                yield code_entity
            elif interest_type == "reference":
                # Create and yield a RawSymbolReference
                # Call self._resolve_context_for_reference to build the context object
                # ...
                yield raw_symbol_reference

    # --- Recurse to Children ---
    for child in node.children:
        async for item in self._walk_and_process(child, context, content_bytes, interest_nodes):
            yield item

    # --- Update Context on Exit ---
    # ... logic to pop from context.scope_stack if node was a scope ...
```
---

























































































---

### **The Final Implementation Roadmap**

This is the step-by-step plan to create and modify all the necessary files to build our V2 system.

#### **Phase 1: Establish the Foundation**

**(These are files that need to exist but have minimal logic, or are utilities)**

**1. Create `.roo/cognee/src/parser/linking_engine.py`:**
*   **Action:** Create a new, initially empty file at this path.
*   **Purpose:** This file will house all our asynchronous background workers (the Janitor, the Heuristic Resolver, the LLM Resolver). For now, it just needs to exist. We will implement its functions in a later phase.

**2. Create/Finalize `.roo/cognee/src/parser/parsers/generic_parser.py`:**
*   **Action:** Ensure this file exists and is correct. It's our fallback for non-AST files.
*   **Content:**
    ```python
    # .roo/cognee/src/parser/parsers/generic_parser.py
    from typing import AsyncGenerator, List, Set
    from .base_parser import BaseParser
    from ..entities import ParserOutput
    from ..utils import logger

    # These constants can live directly in the file that uses them.
    GENERIC_CHUNK_SIZE = 1000
    GENERIC_CHUNK_OVERLAP = 100

    class GenericParser(BaseParser):
        SUPPORTED_EXTENSIONS: List[str] = ["generic_fallback"]
        # ... (full implementation of the parse method)
    ```
*   **Status:** This is a simple, self-contained parser. We can consider its design final.

**3. Finalize `.roo/cognee/src/parser/utils.py`:**
*   **Action:** Review the existing `utils.py` and add the new `resolve_import_path` helper.
*   **Key Addition:**
    ```python
    import os
    from pathlib import Path

    def resolve_import_path(source_file_rel_path: str, import_rel_path: str) -> Optional[str]:
        """Resolves a relative import path against the path of the source file."""
        try:
            # os.path.normpath handles '..' and '.' correctly.
            source_dir = Path(source_file_rel_path).parent
            resolved_path = os.path.normpath(os.path.join(source_dir, import_rel_path))
            return str(Path(resolved_path))
        except Exception:
            return None
    ```
*   **Status:** With this addition, the utilities are complete for our V1 needs.

---

#### **Phase 2: Refactor the Core Pipeline**

**(These files need significant changes to align with the new architecture)**

**1. Refactor `.roo/cognee/src/parser/parsers/cpp_parser.py`:**
*   **Action:** This is the most significant refactoring task. The goal is to transform it from a "Reporter and Guesser" into a "Sufficient Context Reporter."
*   **Plan:**
    1.  **Change Imports:** Update the imports at the top to use the new, final `entities.py` models (`CodeEntity`, `RawSymbolReference`, `ReferenceContext`, `ImportType`).
    2.  **Introduce `FileContext`:** Add the `FileContext` helper class inside the file to manage the file-local symbol table.
    3.  **Implement `_get_fqn_for_node`:** Integrate your full, sophisticated FQN and parameter parsing logic, but modify it to accept the `scope_stack` from the `FileContext` instead of walking the tree itself.
    4.  **Implement `_resolve_context_for_reference`:** Implement the V2 version of this helper. It will take a `target_expression` and the current `FileContext` and use the file-local symbol table to produce the richest possible `ReferenceContext` object.
    5.  **Implement the Single-Pass `parse` method:** Re-architect the main `parse` method to use the "Query-Driven, Single-Pass" model we designed. It will first run all queries, then perform a single recursive walk of the AST to build the `FileContext` and process the matched nodes, yielding `CodeEntity` and `RawSymbolReference` objects.
*   **Status:** This is a major engineering task, but the blueprint is complete and clear.

**2. Refactor `.roo/cognee/src/parser/orchestrator.py`:**
*   **Action:** Rewrite the `process_single_file` function to be our Tier 1 Real-Time Resolver.
*   **Plan:**
    1.  **Update Imports:** Ensure all imports align with the final `entities.py` and the new `graph_utils.py` API.
    2.  **Implement the Full Workflow:** Code the step-by-step logic we defined: transaction management, idempotency/versioning, calling the parser, finalizing `CodeEntity` IDs, running the Tier 1 resolver for *only* high-confidence relative links, creating `PendingLink` nodes for all other references, and updating the `IngestionHeartbeat`.
*   **Status:** The blueprint is complete. This involves translating our detailed plan into Python code.

**3. Refactor `.roo/cognee/src/parser/cognee_adapter.py`:**
*   **Action:** Update the adapter to handle all our new entity types and to correctly populate metadata for indexing.
*   **Plan:**
    1.  **Update Imports:** Correctly import `Node` and `Edge` from the `cognee` library and all our `AdaptableNode` types from `entities.py`.
    2.  **Expand `adapt` function:** The main loop must now correctly handle `PendingLink` and `ResolutionCache` nodes, dumping their full Pydantic model into the `attributes` of the `cognee.Node`.
    3.  **Implement Intelligent Indexing:** Add the logic to create the `index_fields` list in the attributes, specifying which fields (`status`, `canonical_fqn`, etc.) should be indexed for the queries that our Linking Engine will perform.
*   **Status:** The blueprint is complete and straightforward to implement.

---

#### **Phase 3: Implement the Asynchronous Linking Engine**

**(This involves creating the new `linking_engine.py` file and its workers)**

**1. Implement the "Janitor" Worker:**
*   **Action:** Create the `run_janitor_worker` `async` function inside `linking_engine.py`.
*   **Plan:** Implement the simple polling loop. It will call `graph_utils.find_nodes_with_filter` to find active `IngestionHeartbeat` nodes, check their timestamps, and call a new helper function in `graph_utils` to perform a bulk update of `PendingLink` statuses when quiescence is detected.

**2. Implement the "Heuristic Resolver" Worker (Tier 2):**
*   **Action:** Create the `run_heuristic_resolver_worker` `async` function.
*   **Plan:** Implement the polling loop that looks for `PendingLink`s with the `READY_FOR_HEURISTICS` status. For each link, it will execute the prioritized chain of deterministic queries we designed (e.g., `resolve_external_link_by_import_id`, `resolve_internal_link_by_exact_fqn`). Based on the result (zero, one, or many matches), it will either create the final `Relationship` or promote the `PendingLink` to the next tier.

**3. Implement the "LLM Resolver" Worker (Tier 3):**
*   **Action:** Create the `run_llm_resolver_worker` `async` function.
*   **Plan:** Implement the polling loop for `READY_FOR_LLM` links. This involves the full lifecycle: checking the `ResolutionCache`, performing the batched prompt construction, calling the `cognee.llm` interface, verifying the LLM's response against the graph, and creating the final `Relationship` and `ResolutionCache` nodes.
