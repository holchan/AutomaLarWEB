### **Blueprint: Knowledge Graph Data Layer**

### **1. The Core Philosophy: "Progressive Enrichment of Provable Truth"**

At its heart, this system is designed to solve one of the hardest problems in software engineering: creating a deep, reliable, and queryable understanding of a complex, evolving codebase. Our goal is not merely to parse files; it is to create a living, queryable **"digital brain"** for a repository, which understands not just what the code *is*, but *how it connects* and *why*.

This philosophy was forged through a rigorous process of debate and refinement. It is founded on a deep skepticism of "magic" solutions and a commitment to building a system that is, above all, **trustworthy**. We have explicitly rejected fragile heuristics, external configuration files, and any process that requires a developer to be an expert on our system's internals.

This philosophy rests on three foundational pillars:

---

#### **Pillar 1: The Principle of the Focused Expert (The Parser's Role)**

*   **What It Is:** Each parser is a "Sufficient Context Reporter." It is a master of a single language's syntax, and its **only job** is to analyze the Abstract Syntax Tree (AST) of a single file and report facts. It is a master of syntax, not cross-file semantics.

*   **The Context & Why It's Crucial:** We realized that trying to build linking logic (e.g., "what file does this `#include` point to?") inside every single parser would be a nightmare of duplicated, fragile, and language-specific code. It would make adding a new language a monumental task.

    Instead, we radically simplify the parser's role. It doesn't link; it **reports**. For every definition it finds, it yields a `CodeEntity`. For every reference it finds (a call, an inheritance, an import), it yields a rich, structured `RawSymbolReference` object. This report is its "dossier" on the reference, containing every contextual clue it can gather *from within that single file*:
    *   Is the import syntactically `relative` or `absolute`?
    *   What is the literal text of the symbol being referenced?
    *   What `using namespace` directives are active in its scope?

*   **The Analogy:** The parser is an **expert witness at a crime scene**. It doesn't solve the case. It perfectly and factually reports: "I found these footprints, of this size, pointing in this direction. I also found these fingerprints on the doorknob."

---

#### **Pillar 2: The Principle of Centralized Intelligence (The Orchestrator's Role)**

*   **What It Is:** The Orchestrator is the single, universal "Deterministic Resolver." It is completely language-agnostic. Its only job is to take the standardized reports (`RawSymbolReference`) from any parser and apply a single, consistent set of rules to them.

*   **The Context & Why It's Crucial:** This solves the maintainability and consistency problem. All the "clever" linking logic lives in one place. If we improve our heuristic for resolving a C++ call, that same improvement can be applied to a Java call without touching the parsers. This is a **Tier 1, Real-Time** resolver, meaning it only attempts to create links that can be resolved with **zero ambiguity** based on the context provided (e.g., a direct relative path). For everything else, it creates a `PendingLink` "debt" node, honestly acknowledging what it doesn't know yet.

*   **The Analogy:** The Orchestrator is the **detective back at headquarters**. It receives the forensic reports from all the expert witnesses at all the different crime scenes. It is the only one with the "big picture" view (the live graph) and is responsible for connecting the dots.

---

#### **Pillar 3: The Principle of Provable Truth & Graceful Enrichment**

*   **What It Is:** This is the most important philosophical stance. The system will **never create a relationship it cannot prove.** A missing link is infinitely better than a wrong one. The graph must be trustworthy. This leads to a system that enriches itself over time as more proof becomes available.

*   **The Context & Why It's Crucial:** This principle solves the "race condition" and "expensive operation" problems that plagued our earlier designs.
    1.  **Provable Truth:** The Tier 1 resolver only makes high-confidence links. For everything else, it creates a `PendingLink` debt. The graph is always in a correct, if momentarily incomplete, state. It never lies.
    2.  **Graceful Enrichment:** The system autonomously "pays" these debts later. The **Linking Engine** is a set of asynchronous background workers that only run when the system is ready.
        *   **The Trigger is Quiescence:** The system knows it's "ready" by using an `IngestionHeartbeat` node. Only after a repository has stopped receiving new file updates for a configurable period (e.g., 60 seconds) are the more complex resolvers triggered. This is a robust, event-driven solution, not a dumb timer.
        *   **The Tiers are Patient:** The Tier 2 (Heuristic) and Tier 3 (LLM) resolvers only operate on these "matured" debts, ensuring they have the most complete possible view of the graph before making a decision. This prevents wasted LLM calls on problems that would have solved themselves.
    3.  **The Cache is the Memory:** The `ResolutionCache` ensures that once an expensive question is answered (especially by an LLM), it is never asked again, making the system efficient and intelligent over time.

*   **The Analogy:** The graph starts as a collection of accurate but disconnected **island chains** (the files). The Tier 1 resolver builds the bridges within each island chain. The Tier 2 and Tier 3 resolvers are the **ferry services** and **international airlines** that run on a schedule, patiently waiting to build the robust connections between the islands once they are fully mapped.


### **2. The Final Data Contracts (`entities.py`): The Universal Language of the System**

This file is the most critical piece of the entire project. It is the **formal contract** that defines how our disparate components—the Parsers, the Orchestrator, the Linking Engine, and the Graph Adapter—communicate. Every model in this file was designed through a rigorous process of elimination and refinement to be as robust, clear, and universally applicable as possible.

The core principle behind these data models is to **separate factual reporting from interpretive resolution.** Parsers report facts using `CodeEntity` and `RawSymbolReference`. The Orchestrator and Linking Engine interpret these facts to create the final graph, using `PendingLink` and `ResolutionCache` to manage the process.

Here is a detailed breakdown of each key data model and its purpose.

---

#### **The Input Contract: `FileProcessingRequest`**

This is the sole entry point for all work into the system. It is a self-contained "work order" that provides the Orchestrator with everything it needs to process a single file without needing any other external context.

```python
class FileProcessingRequest(BaseModel):
    # --- Core File Identification ---
    absolute_path: str
    repo_path: str
    repo_id: str # e.g., "automalar/web"

    # --- Versioning Context ---
    branch: str # e.g., "main"
    commit_index: str # e.g., "00765"

    # --- Action to Perform ---
    is_delete: bool

    # --- CRITICAL, OPTIONAL HINTS for External Linking ---
    import_id: Optional[str] = None
    root_namespace: Optional[str] = None
```
**Context and Rationale:**
*   The first set of fields (`absolute_path`, `repo_path`, etc.) are the mandatory coordinates needed to place the file's nodes correctly within the graph's hierarchy.
*   `is_delete` is a simple boolean flag that cleanly separates the "delete" action from the "upsert" action, making the Orchestrator's logic simpler.
*   **`import_id` (formerly `canonical_name`):** This is our key compromise for robust external linking. When the caller ingests a library (like `pandas`), it provides this hint (`import_id="pandas"`). This "stamps" the resulting `Repository` node in the graph, making it discoverable by other projects that `import pandas`. It is the crucial, human-provided piece of information that makes cross-repository linking possible without magic.
*   **`root_namespace`:** This solves the "Java problem." For languages where the import syntax is always absolute (e.g., `import com.mycompany.project.utils.Helper`), this hint tells the Orchestrator the "base package" for the current project (`"com.mycompany.project"`). This allows it to deterministically distinguish an internal import from an external one, a problem that is otherwise unsolvable without fragile heuristics.

---

#### **The Parser's Report: `RawSymbolReference` and `ReferenceContext`**

This is the universal "forensic report" that every parser, regardless of language, must generate. It replaces the old, ambiguous `Relationship` and `CallSiteReference` outputs.

```python
class ImportType(str, Enum):
    RELATIVE = "relative"  # `from .` in Python, `#include ""` in C++
    ABSOLUTE = "absolute"  # `import pandas`, `#include <>`, `import java.util.*`

class ReferenceContext(BaseModel):
    import_type: ImportType
    path_parts: List[str]
    alias: Optional[str] = None

class RawSymbolReference(BaseModel):
    source_entity_id: str
    target_expression: str
    reference_type: str # "INHERITANCE", "FUNCTION_CALL", "INCLUDE"
    context: ReferenceContext
```
**Context and Rationale:**
*   We replaced a generic `dict` with a **strongly-typed `ReferenceContext` object**. This was a critical decision for robustness. It creates a formal contract that every parser *must* adhere to, eliminating "magic string" keys and preventing an entire class of bugs. It makes the system self-documenting and easier to maintain.
*   `import_type: ImportType`: We elevated this from a simple boolean (`is_external`) to an `Enum`. This allows parsers to provide more nuanced, syntactic facts (`relative` vs. `absolute`) without having to make a premature decision about whether a link is internal or external. The Orchestrator makes that final decision.
*   `path_parts: List[str]`: This is a universal way to represent a namespace or module path (`['com', 'google', 'guava']`) that works for any language, unlike a single FQN string with language-specific delimiters.
*   `target_expression`: This stores the *literal text* from the code (`pd.DataFrame`). This is crucial because it's the ground truth of what the developer wrote. The linking engine's job is to resolve this expression to a final entity.

---

#### **The Linking Engine's State Machine: `PendingLink` and `ResolutionCache`**

These are the internal "bookkeeping" nodes that allow our system to be autonomous, self-healing, and efficient. They are the heart of the asynchronous Tier 2 and Tier 3 resolvers.

```python
class LinkStatus(str, Enum):
    PENDING_RESOLUTION = "pending_resolution"
    READY_FOR_HEURISTICS = "ready_for_heuristics"
    READY_FOR_LLM = "ready_for_llm"
    UNRESOLVABLE = "unresolvable"
    RESOLVED = "resolved"

class PendingLink(BaseModel):
    id: str # A deterministic hash of the linking question
    status: LinkStatus
    created_at: datetime
    reference_data: RawSymbolReference

class ResolutionCache(BaseModel):
    id: str # The same deterministic hash as the PendingLink
    resolved_target_id: str
    method: ResolutionMethod
```
**Context and Rationale:**
*   **`PendingLink`:** This is our "debt" node. Instead of the Orchestrator failing silently when a link can't be made, it creates a permanent, queryable record in the graph. This is the key to our **eventually consistent** design. The system never forgets a link it needs to make.
*   **`LinkStatus` (Enum):** Using an `Enum` for the status is a critical robustness improvement. It defines the explicit lifecycle of a `PendingLink` (e.g., `PENDING -> READY_FOR_HEURISTICS -> READY_FOR_LLM -> RESOLVED`). This prevents bugs from typos and makes the state machine logic clear and safe.
*   **`ResolutionCache`:** This is our solution to the "wasted LLM call" problem. It is our system's persistent **memory**. When an expensive operation (like an LLM call) successfully answers a linking question, the answer is stored in this cache. The deterministic `id` (a hash of the question) ensures that the next time the exact same linking problem arises, the system will find the answer in the cache first, saving time and money.

### **3. The Component Responsibilities**

### **A. The Parser (e.g., `CppParser`) - The "Sufficient Context Reporter"**

#### **i. The Core Philosophy**

The single most important architectural decision we made was to redefine the parser's job. In earlier, flawed designs, the parser was a "Reporter and Guesser." It tried to find code and then guess at the relationships between them. This made the parser fragile, complex, and difficult to maintain, especially in a multi-language environment.

The new philosophy is that the parser is a **Focused Expert Reporter.** Its responsibility is to be the world's leading expert on the syntax of a single file for a single language. It makes **zero assumptions** about any other file, repository, or the state of the graph. It is a stateless, pure function that transforms source code text into a stream of high-fidelity, factual data.

Its contract is to yield only two types of objects:
1.  **`CodeEntity`:** A factual report of a code structure that has been *defined* in this file.
2.  **`RawSymbolReference`:** A factual report of a *reference* to another symbol, bundled with all the contextual clues the parser can gather from its immediate surroundings.

Crucially, **it never yields `Relationship` objects.** The parser does not link; it only provides the evidence needed for a separate component (the Orchestrator) to do the linking.

#### **ii. What the Parser DOES (Its Mandate)**

**1. Yield `slice_lines` for Chunking:**
*   **Action:** As its very first action, the parser must identify all top-level definition nodes (classes, functions, namespaces, etc.) in the file. It yields a single `List[int]` containing the starting line number of each of these definitions.
*   **Rationale:** This provides a simple, universal blueprint for the `chunking.py` module to intelligently split the file into meaningful, semantically-grouped chunks. It's a pragmatic and efficient way to ensure code blocks aren't nonsensically split in half.

**2. Yield `CodeEntity` for Every Definition:**
*   **Action:** Using its language-specific Tree-sitter queries, the parser identifies every single definition of a class, struct, function, enum, macro, etc. For each one, it yields a `CodeEntity`.
*   **The Temporary ID (`FQN@line`):** The `id` field of this `CodeEntity` is a temporary but crucial piece of information. For example: `MyNamespace::MyClass@50`.
    *   **The FQN Part:** This is a "best-effort" Fully Qualified Name generated by the parser's internal logic (e.g., by walking up the AST from the definition to find parent scopes *within that file*). We made the conscious compromise that this FQN is a powerful heuristic, not a perfect, compiler-level symbol. It is the parser's expert report on the symbol's name within its local file context.
    *   **The `@line` Part:** This is the 0-indexed starting line number of the definition. It is essential for the Orchestrator to later map this `CodeEntity` to its correct `TextChunk`.
*   **Example Code (`CppParser`):**
    ```python
    # Inside the parser's walk/processing loop
    # ... finds a class_specifier node ...
    fqn = self._get_fqn_for_node(name_node, class_node, content_bytes, context.scope_stack)
    temp_id = f"{fqn}@{class_node.start_point[0]}"
    yield CodeEntity(id=temp_id, type="ClassDefinition", ...)
    ```

**3. Yield `RawSymbolReference` for Every Reference:**
*   **Action:** This is the parser's most sophisticated job. For every include, inheritance, function call, macro call, or type annotation, it must yield a `RawSymbolReference`.
*   **Populating the `ReferenceContext`:** This is where the **File-Local Symbol Table** comes into play. As the parser walks the AST from top to bottom, it builds an in-memory map of the file's context.
    1.  It sees `#include "utils.h"` and adds `"utils.h"` to its local map of `relative` includes.
    2.  It sees `using namespace MyProject;` and adds `MyProject` to a list of active namespaces for the current scope.
    3.  When it encounters a reference (e.g., a call to `helper()`), it uses this local symbol table to create the richest possible `ReferenceContext`. It performs a prioritized search: "Does `helper` come from a known local variable? A known include? A `using` namespace?"
*   **The Output:** The result is a `RawSymbolReference` that contains not just the name of the symbol (`target_expression`), but also a structured `ReferenceContext` that gives the Orchestrator powerful clues about how to find the real target.
*   **Example Code (`CppParser`):**
    ```python
    # ... inside the processing loop, finds an #include <vector> node ...
    yield RawSymbolReference(
        source_entity_id=source_file_id,
        target_expression="vector",
        reference_type="INCLUDE",
        context=ReferenceContext(
            import_type=ImportType.ABSOLUTE, # From the <> syntax
            path_parts=["vector"]
        )
    )

    # ... finds `class Derived : public Base` ...
    yield RawSymbolReference(
        source_entity_id="MyNamespace::Derived@50",
        target_expression="Base",
        reference_type="INHERITANCE",
        # The parser runs its internal resolver to create this context
        context=self._resolve_context_for_reference("Base", heritage_node, file_context)
    )
    ```

#### **iii. Known Limitations and Conscious Compromises (The Honest Assessment)**

A robust blueprint must be honest about its boundaries. We have made several conscious trade-offs to prioritize simplicity, speed, and language-agnosticism over perfect, compiler-level accuracy.

*   **The C++ Preprocessor:** This is the most significant compromise. The parser operates on the code **as written**, not as compiled.
    *   **What IS Covered:** We will create `CodeEntity` nodes for `MacroDefinition` and `RawSymbolReference` nodes for `MACRO_CALL`. We can even find symbol references *inside* simple macro bodies (`REFERENCES_SYMBOL`). This provides immense value.
    *   **What is NOT Covered:** Conditional compilation (`#ifdef`) and token-pasting (`##`). The graph will represent all possible code paths from `#ifdef` blocks, and it will not understand symbols generated by token-pasting. We have decided that requiring a pre-processing step is an unacceptable burden on the user.

*   **File-Local FQN Generation:** The parser's `_get_fqn_for_node` is a powerful heuristic, not a perfect algorithm.
    *   **What IS Covered:** It will correctly identify namespaces and parent classes for the vast majority of standard code structures.
    *   **What is NOT Covered:** It will be tricked by complex uses of `using namespace` and advanced C++ features like Argument-Dependent Lookup (ADL). The generated FQN is a high-fidelity "local name," not a guaranteed "canonical name." This is an acceptable trade-off to avoid the complexity of a stateful, multi-file parser.

*   **Wildcard Imports:** For languages like Python, we explicitly do not support resolving symbols from wildcard imports (`from .utils import *`). The parser cannot provide sufficient context, and our core principle is to **never guess**. The parser will simply not yield a `RawSymbolReference` for calls to symbols imported this way.


### **B. The Orchestrator (`orchestrator.py`) - The "Tier 1 Real-Time Resolver"**

#### **i. The Core Philosophy**

The Orchestrator's philosophy is one of **Speed, Safety, and Honesty.** It operates under a strict set of rules designed to ensure that the graph is always in a consistent state and that every action taken is based on high-confidence, provable information.

*   **Speed:** It is designed to be the fast, real-time part of the system. Its job is to process a single file as quickly as possible. To achieve this, it **defers** any complex or ambiguous linking tasks. It does the "easy" work now and leaves the "hard" work for the asynchronous workers.
*   **Safety (Atomicity):** Its primary job is to process a `FileProcessingRequest` **atomically**. This means the entire operation—from deleting old versions to adding new nodes and creating links—is wrapped in a single database transaction. If any part of the process fails (e.g., a parser error, a bug in the Orchestrator), the entire transaction is rolled back. The graph is never left in a broken, half-updated state. This is a non-negotiable guarantee.
*   **Honesty (Tier 1 Resolution):** The Orchestrator is a **High-Confidence, Low-Ambiguity** resolver. It will only attempt to create a final `Relationship` if the context provided by the parser is so clear that the link is effectively proven (e.g., a direct relative import). For every other reference, it honestly admits, "I do not have enough information to resolve this with 100% certainty right now." Instead of guessing or failing, it creates a `PendingLink` "debt" node, which is a factual statement of an unresolved dependency.

#### **ii. What the Orchestrator DOES (Its Mandate, Step-by-Step)**

The `process_single_file` function is the main entry point and must execute a precise sequence of operations.

**1. Pre-computation and Transaction Start:**
*   **Action:** It receives the `FileProcessingRequest`. It immediately initiates a database transaction (`with session.begin_transaction() as tx:`). All subsequent graph operations will use this `tx` handle. It also computes the `repo_id_with_branch` and `relative_path` strings.
*   **Rationale:** Starting the transaction immediately ensures that even the initial checks and deletions are part of the atomic unit of work.

**2. Handle `DELETE` and Empty File Scenarios:**
*   **Action:** It checks `request.is_delete`. If `True`, it calls `graph_utils.delete_nodes_with_filter` to remove all nodes associated with that file path and then commits the transaction and exits. It also performs this deletion if the file content is empty or unreadable.
*   **Rationale:** This handles file deletions and cleanups as a simple, atomic operation, keeping the main `UPSERT` logic clean.

**3. Idempotency Check and Versioning (for `UPSERT`):**
*   **Action:** It calculates the SHA256 hash of the file's content. It calls `graph_utils.check_content_exists` to query the graph for any `SourceFile` node with the same hash. If found, it aborts the operation, as this exact content has already been processed. If not found, it calls `graph_utils.get_latest_local_save_count` to determine the next save number (e.g., `-002`).
*   **Rationale:** This makes the system robust and efficient. Saving the same file twice has no effect, preventing duplicate data and wasted processing. The versioning logic is centralized here, not guessed by the caller.

**4. Call the Parser and Collect Outputs:**
*   **Action:** It calls `_get_parser_for_file` to dynamically select the correct parser. It then calls `parser.parse()` and collects all yielded items into three separate lists: `slice_lines`, `code_entities`, and `raw_references`.
*   **Rationale:** It aggregates all the "raw materials" from the expert reporter before beginning the assembly process.

**5. Assemble the File's "Island" (Phase A):**
*   **Action:** This is a multi-step assembly process.
    1.  It creates the `Repository` and `SourceFile` nodes.
    2.  It calls `generate_text_chunks_from_slice_lines` to create the `TextChunk` nodes.
    3.  It creates the first set of high-confidence, structural relationships: `(SourceFile) -> [CONTAINS_CHUNK] -> (TextChunk)`.
    4.  **Crucially, it finalizes the `CodeEntity` IDs.** It iterates through the `code_entities` from the parser, finds their parent `TextChunk` based on line number, and constructs their final, permanent, version-aware ID (e.g., `...|chunk|fqn`). It builds a `temp_id_to_final_id_map`.
    5.  It creates the second set of structural relationships: `(TextChunk) -> [DEFINES_CODE_ENTITY] -> (CodeEntity)`.
*   **Rationale:** This block constructs the entire "island" of nodes for the file being processed, complete with final IDs. This is the foundation upon which all linking will be built.

**6. Run the Tier 1 Resolver and Create Debts:**
*   **Action:** It iterates through the `raw_references` collected from the parser.
    1.  It uses the `temp_id_to_final_id_map` to update the `source_entity_id` of each reference to its final form.
    2.  It calls a helper, `_resolve_tier1_link`, for each reference. This helper only contains the logic for the most certain resolutions (e.g., direct relative path imports).
    3.  **If `_resolve_tier1_link` returns a target ID:** A final `Relationship` object is created in memory.
    4.  **If `_resolve_tier1_link` returns `None`:** A `PendingLink` object is created in memory. This object stores the complete, context-rich `RawSymbolReference`.
*   **Rationale:** This cleanly separates high-confidence linking from everything else. The Orchestrator does the "easy" work immediately and creates explicit, structured "to-do" items (`PendingLink`s) for all the "hard" work.

**7. Final Commit:**
*   **Action:** It takes the final list of all new nodes (`CodeEntity`, `PendingLink`, etc.) and all new `Relationship`s, passes them to the `cognee_adapter`, and then saves the result to the graph using `graph_utils.save_graph_data`. Its very last action is to call `graph_utils.update_heartbeat` to signal that activity has occurred for this repository. Finally, the `with` block ensures the transaction is committed.
*   **Rationale:** This ensures that the entire state change—new nodes, new high-confidence links, and new "debt" nodes—is saved to the graph in a single, atomic operation.

#### **iii. What the Orchestrator DOES NOT DO (Its Boundaries)**

*   **It does NOT perform complex, graph-wide queries.** The Tier 1 resolver only looks for targets in a very specific, limited scope. All broad searches (like suffix matching FQNs) are the responsibility of the Tier 2 worker.
*   **It does NOT call the LLM.** This is a critical boundary. The real-time ingestion path must be fast and deterministic.
*   **It does NOT know about other files in a "batch."** Its logic is entirely focused on the single `FileProcessingRequest` it was given, making it simple, stateless, and easy to test.

### **C. The Linking Engine (`linking_engine.py`) - The Asynchronous Workers**

#### **i. The Core Philosophy**

The Linking Engine's philosophy is to **never interfere with real-time ingestion**. Its job is to work patiently in the background, cleaning up the "debt" (`PendingLink` nodes) left by the fast-moving Orchestrator. It solves the fundamental race condition problem—"how do I resolve a link when the target might not exist yet?"—by simply **waiting until the initial "ingestion storm" is over.**

This is a tiered system where each tier operates on a different level of confidence and has a different trigger, ensuring that expensive or complex operations are only performed when it's safe and efficient to do so.

---

#### **ii. Component 1: The "Janitor" (The Quiescence Trigger)**

This is the gatekeeper for all advanced linking. It is a simple, robust, and low-impact background process.

*   **Primary Job:** To monitor the activity level of each repository branch and determine when an "ingestion session" has become quiescent (inactive).

*   **The Mechanism (`IngestionHeartbeat` node):**
    1.  Every time the Orchestrator successfully processes a file, it makes one final call: `update_heartbeat()`. This "pings" a special node (e.g., `heartbeat://automalar/web@main`), setting its `last_activity_timestamp` to `now()`.
    2.  This means that as long as files are being rapidly ingested, this timestamp is constantly being refreshed.

*   **The Janitor's Workflow:**
    1.  **Trigger:** Runs on a simple, periodic schedule (e.g., a cron job or `asyncio.sleep(60)`). It is not event-driven; it is a poller.
    2.  **Query:** It performs a single, fast query: "Find all `IngestionHeartbeat` nodes where `status` is `'active'`."
    3.  **The Check:** For each active heartbeat it finds, it asks the crucial question: **"Has it been more than 60 seconds since `last_activity_timestamp`?"**
    4.  **The Action:**
        *   If the answer is **NO**, the ingestion is still active. The Janitor does nothing and goes back to sleep.
        *   If the answer is **YES**, the ingestion has gone quiet. The Janitor now "flips the switch" for the next tier. It updates all `PendingLink` nodes for that repository from `status: PENDING_RESOLUTION` to `status: READY_FOR_HEURISTICS`. It also updates the heartbeat's status to `quiescent` to prevent re-triggering.

*   **Rationale:** This is the robust, time-based solution we designed. It is not a fragile timer. It is a **state check**. It solves the problem of "how do we know when the ingestion is done?" in a simple, reliable way without complex job tracking.

---

#### **iii. Component 2: The "Heuristic Resolver" (Tier 2)**

This worker is the "detective" that solves the majority of the remaining cases using the full power of the now-stable graph.

*   **Primary Job:** To resolve links that were not certain enough for the Tier 1 real-time resolver. It handles absolute imports and ambiguous names.

*   **The Heuristic Resolver's Workflow:**
    1.  **Trigger:** It is a background worker that continuously polls for a simple condition: "Find all `PendingLink` nodes where `status` is `'ready_for_heuristics'`."
    2.  **The Resolution Chain:** For each `PendingLink` it finds, it executes a prioritized chain of graph queries based on the `RawSymbolReference` data stored in the debt node.
        *   **Query 1 (External Link by Canonical Name):** Does the reference point to an absolute import like `pandas`? If so, query for a `Repository` node with `provides_import_id == "pandas"`. If found, search within that repository for the target symbol.
        *   **Query 2 (Internal Link by FQN Suffix - The C++ Case):** Does the reference seem to be a partially qualified name like `MyProject::MyClass`? If so, query for all `CodeEntity` nodes whose FQN *ends with* `::MyProject::MyClass`.
        *   *(More heuristics can be added here over time without changing the architecture.)*
    3.  **The Action:**
        *   **If one and only one target is found:** The link is unambiguous. The worker creates the final `Relationship`, creates a `ResolutionCache` entry with `method: HEURISTIC_MATCH`, and **deletes** the `PendingLink` node. The debt is paid.
        *   **If multiple targets are found:** The link is genuinely ambiguous. The worker updates the `PendingLink`'s status to `READY_FOR_LLM`.
        *   **If zero targets are found:** This is a true "dead end" that the deterministic system cannot solve. The worker updates the `PendingLink`'s status to `READY_FOR_LLM` (to give it one last chance) or potentially `UNRESOLVABLE`.

*   **Rationale:** This tier is where the deep, graph-wide analysis happens. By waiting until the ingestion session is quiescent, its queries are safe from race conditions and have the most complete possible information to work with.

---

#### **iv. Component 3: The "LLM Resolver" (Tier 3)**

This is the court of last resort. It is an optional, "enrichment" service that is explicitly designed to be slow, expensive, and powerful.

*   **Primary Job:** To use generative AI to attempt to resolve the truly difficult or ambiguous links that the deterministic resolvers could not.

*   **The LLM Resolver's Workflow:**
    1.  **Trigger:** A background worker that polls for `PendingLink`s with `status: READY_FOR_LLM`.
    2.  **The Cache Check (Crucial for Cost-Saving):** For each `PendingLink`, it first constructs the deterministic ID for its corresponding `ResolutionCache` node. It queries the graph: "Does a `ResolutionCache` node with this ID already exist?"
        *   If **YES**, the question has already been answered. It uses the `resolved_target_id` from the cache, creates the final `Relationship`, and deletes the `PendingLink`. The LLM is not called.
    3.  **The Prompt Construction:** If there is no cache hit, it constructs a rich, detailed prompt for the LLM, including the source code snippet, the `RawSymbolReference`, and the list of ambiguous candidates found by the Tier 2 resolver.
    4.  **The LLM Call:** It makes the expensive API call to the LLM.
    5.  **The Action:** It parses the LLM's response.
        *   If the LLM provides a single, confident answer, the worker creates the final `Relationship`.
        *   It then **creates a new `ResolutionCache` node** to store the answer, ensuring this question is never asked again.
        *   It deletes the `PendingLink` node.

*   **Rationale:** This tier provides a path to solving problems that are impossible for static analysis alone. By making it asynchronous, triggered only by "stale" and vetted debts, and by implementing a persistent cache, we use this powerful tool intelligently and efficiently.
