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

### **B. The Linking Engine: Component 1 - The "Janitor" (The Quiescence Trigger)**

#### **i. The Core Philosophy**

The philosophy of the Janitor is **"Patient, Non-Intrusive Observation."**

Its job is not to be "smart." Its job is to be a simple, reliable, and low-impact background process that answers one critical question: **"Has the 'ingestion storm' for a given repository branch passed?"**

*   **Patient:** It does not try to predict the end of an ingestion session. It simply waits for a pre-defined period of inactivity (quiescence). This is a robust, time-tested pattern for handling bursty, asynchronous event streams.
*   **Non-Intrusive:** It never modifies the core code graph (`CodeEntity`, `Relationship`, etc.). Its only job is to observe the `IngestionHeartbeat` nodes and update the `status` of `PendingLink` nodes. It acts as a "promoter," moving work from one queue to another.
*   **Observer:** It is the only component that uses time as a trigger. This is a conscious architectural decision. We have isolated the system's only time-based logic into this single, simple component, making the rest of the system purely event-driven and deterministic.

#### **ii. The Workflow and Code Implementation**

The Janitor is a long-running asynchronous task. In a real production system, this would be a standalone microservice or a managed background worker. For our design, we can represent it as a single `async` function that runs in a loop.

**1. The `IngestionHeartbeat` Node:**
*   This is the simple "state machine" that the Janitor observes. It's a single node per repository branch in the graph.
*   The Orchestrator's only responsibility is to "ping" this node at the end of every successful `process_single_file` transaction by calling `graph_utils.update_heartbeat()`. This keeps the `last_activity_timestamp` fresh.

**2. The Janitor's Main Loop:**
*   **Code Implementation (in `linking_engine.py`):**
    ```python
    # .roo/cognee/src/parser/linking_engine.py
    import asyncio
    from datetime import datetime, timezone, timedelta

    from .utils import logger
    from .entities import LinkStatus
    # We need the graph utils to interact with the database
    from .graph_utils import find_nodes_with_filter, update_pending_link_status, update_node_metadata

    QUIESCENCE_PERIOD_SECONDS = 60 # This should be configurable

    async def run_janitor_worker(stop_event: asyncio.Event):
        """
        The main loop for the Janitor worker. Runs periodically to detect
        quiescent ingestion sessions and promote pending links.
        """
        log_prefix = "LINKING_ENGINE(Janitor)"
        logger.info(f"{log_prefix}: Starting worker...")

        while not stop_event.is_set():
            try:
                logger.debug(f"{log_prefix}: Running periodic check for quiescent repositories.")

                # 1. Find all active heartbeats
                active_heartbeats = await find_nodes_with_filter({
                    "type": "IngestionHeartbeat",
                    "status": "active"
                })

                now = datetime.now(timezone.utc)

                for heartbeat_node in active_heartbeats:
                    last_activity_str = heartbeat_node.attributes.get("last_activity_timestamp", "")
                    if not last_activity_str:
                        continue

                    last_activity_dt = datetime.fromisoformat(last_activity_str)

                    # 2. The Check: Has it been inactive long enough?
                    if now - last_activity_dt > timedelta(seconds=QUIESCENCE_PERIOD_SECONDS):
                        repo_id_with_branch = heartbeat_node.id.replace("heartbeat://", "")
                        logger.info(f"{log_prefix}: Quiescence detected for '{repo_id_with_branch}'. Promoting pending links.")

                        # 3. The Action: Promote the links and update the heartbeat
                        await promote_pending_links_for_repo(repo_id_with_branch)
                        await update_node_metadata(
                            heartbeat_node.id,
                            {"status": "quiescent"}
                        )

            except Exception as e:
                logger.error(f"{log_prefix}: An error occurred during the check: {e}", exc_info=True)

            # Wait for the next cycle
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=QUIESCENCE_PERIOD_SECONDS)
            except asyncio.TimeoutError:
                pass # This is expected, just means it's time for the next loop

        logger.info(f"{log_prefix}: Stop event received. Shutting down.")

    async def promote_pending_links_for_repo(repo_id_with_branch: str):
        """
        Finds all PENDING_RESOLUTION links for a repo and promotes them
        to READY_FOR_HEURISTICS.
        """
        # This function would need a way to update nodes in bulk, or it would
        # iterate and update them one by one.

        pending_links_to_promote = await find_nodes_with_filter({
            "type": "PendingLink",
            "status": LinkStatus.PENDING_RESOLUTION.value,
            "repo_id_str": repo_id_with_branch # Assuming PendingLink nodes have this metadata
        })

        if not pending_links_to_promote:
            return

        logger.info(f"Promoting {len(pending_links_to_promote)} pending links for '{repo_id_with_branch}'.")

        for link_node in pending_links_to_promote:
            # This is where a bulk update method would be more efficient.
            await update_pending_link_status(link_node.id, LinkStatus.READY_FOR_HEURISTICS)

    ```
    *(Note: This implementation assumes `PendingLink` nodes will be tagged with their `repo_id_str` in their metadata for efficient querying. This is a small but important detail for the `cognee_adapter` to handle.)*

#### **iii. The Rationale and Trade-offs (The Honest Assessment)**

*   **What this Solves:** This is the most robust, non-invasive way to solve the "when is the ingestion session over?" problem. It does not require a complex external job scheduler or stateful orchestration logic. The state is stored and managed entirely within the graph itself.
*   **The Trade-off (Latency):** The primary compromise is a built-in delay. A link that requires Tier 2 resolution will not be created instantly. It will only be created after the `QUIESCENCE_PERIOD_SECONDS` has elapsed *and* the Janitor and Heuristic Resolver workers have run. For most use cases, a delay of 1-2 minutes for complex, graph-wide linking is a very acceptable price to pay for correctness and architectural simplicity.
*   **The Robustness:** This system is highly robust to failure. If the Janitor worker crashes, it will simply restart on its next scheduled run and pick up where it left off by querying the graph for active heartbeats. No state is lost. If a file is updated during the quiescent period, its `process_single_file` call will simply flip the heartbeat's status back to `active`, correctly and automatically pausing any further Tier 2 resolution until the system goes quiet again.

---

### **C. The Linking Engine: Component 2 - The "Deterministic Graph Resolver" (Tier 2)**

#### **i. The Core Philosophy**

The philosophy of this component is **"Certainty Through a Complete Worldview."**

Unlike the Tier 1 resolver, which only has the context of a single file, this Tier 2 worker runs **after** an entire ingestion session is complete and the graph is "quiescent." It therefore has a complete, stable "worldview" of all the code in the repository for that session.

Its primary job is to resolve links that were ambiguous at the single-file level but become clear when the entire repository's context is available. It is not a "heuristic" engine in the sense of guessing. It is a **deterministic query engine** that runs a prioritized chain of high-confidence queries. It only succeeds if it finds **one and only one** logical answer.

---

#### **ii. The Workflow and Code Implementation**

**1. The Trigger:**
*   This worker is triggered by the **`Janitor`**. After the `IngestionHeartbeat` for a repository goes quiescent, the Janitor promotes all of that repo's `PendingLink`s from `PENDING_RESOLUTION` to `READY_FOR_HEURISTICS`.
*   This worker is a simple, stateless background process that polls for this specific status.
    > **Query:** "Find all `PendingLink` nodes where `status` is `'ready_for_heuristics'`."

**2. The Prioritized Resolution Chain:**
*   For each `PendingLink` it finds, it takes the `RawSymbolReference` data and begins a chain of queries. It stops at the first query that returns a single, unambiguous result.

**The Code Logic (Inside the Tier 2 Worker):**

```python
# A conceptual function inside the Tier 2 worker
async def run_tier2_resolution_for_link(tx, pending_link: PendingLink):
    ref_data = pending_link.reference_data
    context = ref_data.context

    # --- Attempt 1: High-Confidence External Link Resolution ---
    if context.import_type == ImportType.ABSOLUTE:
        # This handles 'import pandas' or 'import com.google.guava'
        top_level_module = context.path_parts[0]
        target_id = await resolve_external_link(tx, top_level_module, ref_data.target_expression)
        if target_id:
            # SUCCESS!
            await create_final_link(tx, pending_link, target_id, ResolutionMethod.HEURISTIC_MATCH)
            return

    # --- Attempt 2: High-Confidence Internal Link Resolution (Exact FQN Match) ---
    # This handles cases where Tier 1 failed due to processing order.
    # e.g., app.py references MyClass, but models.py hadn't been processed yet.
    target_id = await resolve_internal_link_by_fqn(tx, ref_data.target_expression)
    if target_id:
        # SUCCESS!
        await create_final_link(tx, pending_link, target_id, ResolutionMethod.HEURISTIC_MATCH)
        return

    # --- If all deterministic attempts fail, promote to Tier 3 ---
    await promote_link_for_llm(tx, pending_link)
```

Now, let's look at the implementation of those helper functions.

**A. `resolve_external_link` (The `import_id` Query):**

*   **How it Works:** This function looks for a library that has been explicitly "registered" with our system via the `import_id` hint during its ingestion.
*   **Code Implementation (in `linking_engine.py`):**
    ```python
    async def resolve_external_link(tx, module_name: str, full_target_expr: str) -> Optional[str]:
        # Query 1: Find the repository that provides this module name.
        repo_nodes = await find_nodes_with_filter(tx, {"provides_import_id": module_name, "type": "Repository"})

        if len(repo_nodes) != 1:
            if len(repo_nodes) > 1:
                logger.warning(f"Ambiguous import_id '{module_name}'. Found multiple provider repos. Cannot resolve.")
            return None # Fails if zero or more than one repo provides this name.

        target_repo_id = repo_nodes[0].id

        # Query 2: Find the EXPORTED symbol within that repository.
        # This is a complex query that needs to find the CodeEntity with a matching
        # canonical_fqn AND an incoming `EXPORTS` relationship from the library's entry point.
        # This logic would be encapsulated in a graph_utils function.
        target_entity = await find_exported_symbol_in_repo(tx, target_repo_id, full_target_expr)

        return target_entity.id if target_entity else None
    ```

**B. `resolve_internal_link_by_fqn` (The Exact Match Query):**

*   **How it Works:** This is the safety net for internal links that failed in Tier 1 simply due to processing order. Now that the whole repo is ingested, we can search for an exact match of the FQN across the entire project.
*   **Code Implementation (in `linking_engine.py`):**
    ```python
    async def resolve_internal_link_by_fqn(tx, target_fqn: str, repo_id: str) -> Optional[str]:
        # This query looks for a CodeEntity with a matching FQN *within the same repository*.
        # The canonical_fqn would be stored in the node's metadata.
        entity_nodes = await find_nodes_with_filter(
            tx,
            {"canonical_fqn": target_fqn, "repo_id_str": repo_id, "type": "CodeEntity"}
        )

        if len(entity_nodes) == 1:
            return entity_nodes[0].id # Unambiguous success!

        if len(entity_nodes) > 1:
            # This can happen with function overloading. A future enhancement could
            # use argument types from the RawSymbolReference to pick the right one.
            # For now, we declare it ambiguous.
            logger.warning(f"Ambiguous internal FQN '{target_fqn}'. Found {len(entity_nodes)} candidates.")

        return None # Fails if zero or more than one match.
    ```

**C. The Final Action Functions (`create_final_link` and `promote_link_for_llm`):**

*   These are simple helper functions that perform the final graph mutations.
*   **Code Implementation (in `linking_engine.py`):**
    ```python
    async def create_final_link(tx, pending_link: PendingLink, target_id: str, method: ResolutionMethod):
        ref_data = pending_link.reference_data
        # 1. Create the final Relationship
        await save_graph_data(tx, [], [
            (ref_data.source_entity_id, target_id, ref_data.reference_type, ref_data.context.get("properties", {}))
        ])
        # 2. Create the cache entry so we never have to solve this again
        await save_graph_data(tx, [
            ResolutionCache(id=pending_link.id, resolved_target_id=target_id, method=method)
        ], [])
        # 3. Delete the debt node
        await delete_pending_link(tx, pending_link.id)
        logger.info(f"Successfully resolved link {pending_link.id} via {method.value}.")

    async def promote_link_for_llm(tx, pending_link: PendingLink):
        # Here we could add logic to check if the link is "worthy" of an LLM call.
        # For now, we just promote it.
        await update_pending_link_status(tx, pending_link.id, LinkStatus.READY_FOR_LLM)
        logger.info(f"Promoting link {pending_link.id} to LLM tier.")
    ```

#### **iii. The Rationale and Trade-offs**

This Tier 2 design is the embodiment of our **"Accuracy-First"** principle.

*   **What it Covers:** It perfectly handles the two most common types of non-local links: imports from known third-party libraries and calls between files in the same project.
*   **What it DOES NOT Cover (The Compromise):** It **intentionally does not** use "fuzzy" or "heuristic" matching like the `ends with` suffix search. This means that a C++ call like `MyProject::MyClass()` that was made from a file with `using namespace MyCompany;` will **fail** this tier, because the `target_expression` does not match the `canonical_fqn` of `MyCompany::MyProject::MyClass`.
*   **Why this is the Right Choice:** This failure is a good thing. It means the Tier 2 resolver has correctly identified a problem that is **not deterministically solvable** with the information it has. It is a genuinely ambiguous link. By refusing to guess, it maintains the integrity of the graph and correctly passes this "hard problem" to the Tier 3 LLM, which is the only tool equipped to handle it.

---

### **D. The Linking Engine: Component 3 - The "LLM Consultant" and "Repair" Subsystem**

This is the final and most advanced part of our linking engine. It's designed to be **patient, efficient, and event-driven**. Its primary job is not just to call an LLM, but to intelligently manage the entire lifecycle of a "hard problem."

This subsystem is composed of two distinct workers that act on specific graph states.

---

#### **Component 3A: The "LLM Consultant" Worker (The Question Asker)**

*   **Core Philosophy:** This worker's job is to ask **good questions**. It does not try to solve the problem itself. It gathers all available context for a difficult linking problem, calls the LLM for a "consultation," and then stores the LLM's "expert opinion" as a new, richer piece of evidence in the graph.

*   **The Trigger:** This worker is triggered by the **`Janitor`**. After an ingestion session goes quiescent, the Janitor promotes `PendingLink` nodes to `READY_FOR_HEURISTICS`. After the Tier 2 Heuristic Resolver runs, any remaining, truly ambiguous links are promoted to `READY_FOR_LLM`. This worker polls for that specific status.
    > **Query:** "Find all `PendingLink` nodes where `status` is `'ready_for_llm'`."

*   **The Workflow and Code Logic:**
    1.  **Cache Check:** For each `PendingLink`, it first checks the `ResolutionCache` to avoid asking a question that has already been answered. This is our primary cost-saving mechanism.
    2.  **Batched Prompt Construction:** As we designed, it will group all `PendingLink`s from the same source file (`e.g., file_A.cpp`) into a **single, batched API call**.
    3.  **The Prompt:** The prompt is a structured "case file" that includes the full source code of `file_A.cpp`, followed by a list of each unresolved reference, its line of code, and any ambiguous candidates found by the Tier 2 resolver. It will request a structured JSON response using a Pydantic model (`LLMResolutionBatch`).
    4.  **The LLM Call:** It uses the `cognee.llm.get_completion` interface to make the API call.
    5.  **The Action (This is the critical change):** The worker **does not** create the final `Relationship`. It does not try to verify the answer. Its only job is to update the `PendingLink` node with the LLM's advice.

    *   **Code Example (The action after receiving the LLM response):**
        ```python
        # Inside the LLM worker, after receiving the llm_response_batch
        for result in llm_response_batch.results:
            pending_link_id = result.link_id
            llm_hint_fqn = result.resolved_canonical_fqn

            if llm_hint_fqn:
                # The LLM gave a confident answer. Update the debt node.
                # It is no longer waiting for the LLM, it's now waiting for a specific target.
                await update_pending_link(
                    tx,
                    link_id=pending_link_id,
                    new_status=LinkStatus.AWAITING_TARGET,
                    new_metadata={"awaits_fqn": llm_hint_fqn, "confidence": result.confidence}
                )
            else:
                # The LLM itself was unsure. This is a true dead end.
                await update_pending_link(
                    tx,
                    link_id=pending_link_id,
                    new_status=LinkStatus.UNRESOLVABLE,
                    new_metadata={"reason": result.reasoning}
                )
        ```
*   **Result:** The `PendingLink` has now evolved. It's no longer a simple "debt"; it's a "smart debt" that now explicitly states: **"I am waiting for the `CodeEntity` with the canonical FQN `'MyCompany::Core::BaseClass'` to appear in the graph."**

---

#### **Component 3B: The "Repair Worker" (The Link-Maker)**

*   **Core Philosophy:** This worker is a simple, fast, and highly efficient event listener. Its only job is to react to new information being added to the graph and pay off any "smart debts" that were waiting for that exact piece of information.

*   **The Trigger:** This worker is **event-driven**. It is triggered every time the Orchestrator successfully creates and saves a new `CodeEntity` node. (In a real system, this would be a message queue or a database trigger. For our design, we can model it as an async task that is called at the end of `process_single_file`).
    > **The Event:** `event = {'new_entity_created': True, 'canonical_fqn': 'MyCompany::Core::BaseClass', 'entity_id': '...'}`

*   **The Workflow and Code Logic:**
    1.  **Receive the Event:** The worker gets the `canonical_fqn` of the newly created entity.
    2.  **The Query (The "Debt Collector"):** It performs a single, fast, indexed query against the graph.
        > **Query:** "Find all `PendingLink` nodes where `status` is `'awaiting_target'` AND `awaits_fqn` is `'MyCompany::Core::BaseClass'`.

    3.  **The Action (This is the final step):** For every `PendingLink` it finds:
        *   **It now has everything it needs:**
            *   The `source_entity_id` (from the `PendingLink.reference_data`).
            *   The `target_id` (from the `entity_id` in the event).
            *   The `reference_type` (from the `PendingLink.reference_data`).
        *   **It creates the final `Relationship`** and saves it to the graph.
        *   **It creates a `ResolutionCache` node** to store the successful resolution.
        *   **It deletes the `PendingLink` node.** The debt is paid.

*   **Rationale:** This two-worker design is the robust solution to all the problems we discussed.
    *   **No Wasted Calls:** The `LLM Consultant` asks a question once. The answer is stored.
    *   **No Race Conditions:** The `Repair Worker` only creates a link after the target has been verifiably created in the graph.
    *   **Event-Driven and Autonomous:** The system heals itself automatically as new code is ingested. There are no timers or external triggers required for this final linking step.
