# **Knowledge Graph Data Layer Blueprint**

### **1. Executive Summary: The Core Philosophy**

#### **Progressive Enrichment of Provable Truth**

At its heart, this system is designed to solve one of the hardest problems in software engineering: creating a deep, reliable, and queryable understanding of a complex, evolving codebase. Our goal is not merely to parse files; it is to create a living, queryable **"digital brain"** for a repository, which understands not just what the code *is*, but *how it connects* and *why*.

This philosophy was forged through a rigorous process of debate and refinement. It is founded on a deep skepticism of "magic" solutions and a commitment to building a system that is, above all, **trustworthy**. We have explicitly rejected fragile heuristics, external configuration files, and any process that requires a developer to be an expert on our system's internals.

#### **System Benefits and Guarantees**

##### **Reliability Guarantees**
- **Atomic Operations:** Every file processing operation is wrapped in a database transaction
- **Idempotency:** Processing the same file content multiple times has no effect
- **Provable Truth:** The system never creates relationships it cannot prove
- **Graceful Degradation:** Missing links are preferred over incorrect ones

##### **Performance Characteristics**
- **Real-time Tier 1:** Fast, deterministic processing for high-confidence operations
- **Asynchronous Tiers 2-3:** Complex operations run in background without blocking ingestion
- **Intelligent Caching:** LLM responses and resolution results are cached to prevent redundant work
- **Event-driven Architecture:** Self-healing system that responds to new information automatically

##### **Scalability Features**
- **Language Agnostic:** Adding new languages requires only implementing the parser interface
- **Horizontal Scaling:** Workers can be distributed across multiple processes/machines
- **Incremental Processing:** Only changed files need reprocessing
- **Efficient Querying:** Graph structure enables fast traversal and complex queries

#### **The Relationship Catalog: Describing the "Knowledge" in the Graph**

The ultimate goal of this entire system is to produce a rich, queryable set of `Relationship` nodes. These edges are what transform a disconnected collection of code entities into a true knowledge graph. Each relationship type is designed to answer a specific, high-value question a developer would ask about the codebase.

The relationships are created at different stages by different components, based on the level of confidence and context required.

---

#### **Category 1: Structural & Definitional Relationships (The "Where")**

These relationships form the physical and logical backbone of the graph. They are unambiguous and are created with **100% confidence** by the **Orchestrator** during its Tier 1, real-time processing.

**`CONTAINS_CHUNK`**
*   **Direction:** `(SourceFile) -> [CONTAINS_CHUNK] -> (TextChunk)`
*   **Purpose:** Describes the physical hierarchy of a file. It answers the question: "What are the constituent text blocks of this specific version of this file?"
*   **Creation:** The Orchestrator creates these immediately after running the `generate_text_chunks_from_slice_lines` function.

**`DEFINES_CODE_ENTITY`**
*   **Direction:** `(TextChunk) -> [DEFINES_CODE_ENTITY] -> (CodeEntity)`
*   **Purpose:** Links a piece of code to the specific text block where it is defined. It answers: "In which part of `main.py` is the `run()` function actually located?"
*   **Creation:** The Orchestrator creates these after finalizing a `CodeEntity`'s ID by mapping it back to its parent `TextChunk` via line numbers.

---

#### **Category 2: High-Confidence Semantic Relationships (The "How")**

These relationships describe how code elements interact according to the explicit, unambiguous rules of the language. They are created with **~99% confidence**, either by the **Orchestrator (Tier 1)** if the context is perfect, or by the **Linking Engine (Tier 2)** using deterministic, exact-match queries.

**`IMPORTS`**
*   **Direction:** `(SourceFile) -> [IMPORTS] -> (SourceFile)`
*   **Purpose:** Tracks direct, file-level dependencies within the same repository. It answers: "What other files will be immediately affected if I change `utils.py`?"
*   **Creation:** Created by the Tier 1 resolver if the `RawSymbolReference` from the parser has a clear, resolvable relative path.

**`EXTENDS` / `IMPLEMENTS`**
*   **Direction:** `(Child Class: CodeEntity) -> [EXTENDS] -> (Parent Class: CodeEntity)`
*   **Purpose:** Models the inheritance hierarchy, fundamental to Object-Oriented Programming. It answers: "What is the parent class of `MyExtendedClass`?" or "Show me all classes that implement the `Serializable` interface."
*   **Creation:** Created by the Tier 1 or Tier 2 resolver when it can unambiguously link a child class to its parent based on the `RawSymbolReference`.

**`CALLS` (Internal)**
*   **Direction:** `(Calling Function: CodeEntity) -> [CALLS] -> (Called Function: CodeEntity)`
*   **Purpose:** This is the most important relationship for understanding runtime behavior. It answers: "Who calls the `calculate_total()` function?"
*   **Creation:** Same as `EXTENDS`. It is only created by the deterministic resolvers (Tier 1 or 2) when there is a high-confidence, unambiguous link between a caller and a callee *within the same repository*.

**`USES_LIBRARY`**
*   **Direction:** `(SourceFile) -> [USES_LIBRARY] -> (ExternalReference)`
*   **Purpose:** Creates a high-level, factual link to an external dependency. It answers: "Which files in my project have a dependency on the `pandas` library?"
*   **Creation:** Created by the Tier 1 Orchestrator. When it receives a `RawSymbolReference` for an `ABSOLUTE` import and its internal heuristic determines the module is not local, it creates this link to a canonical `external-library://` beacon node. This is a 100% confident statement that a dependency *exists*, without guessing at the details.

---

#### **Category 3: Inferred & AI-Enriched Relationships (The "Hidden How")**

These are the most complex relationships. They are created with **lower or variable confidence** and are primarily the responsibility of the **Tier 2 (Heuristic)** and **Tier 3 (LLM)** resolvers.

**`CALLS` (External or Ambiguous)**
*   **Direction:** `(Calling Function: CodeEntity) -> [CALLS] -> (Called Function: CodeEntity)`
*   **Purpose:** To create deep links into external libraries or resolve ambiguous internal calls.
*   **Creation:**
    *   **Tier 2:** Creates the link if its prioritized chain of graph-wide queries returns a **single, unambiguous result**. This includes checking for `import_id`s, exact `canonical_fqn` matches, and using a verified suffix-match heuristic for partial FQNs.
    *   **Tier 3:** Creates the link based on the verified output of an LLM, for cases that were too ambiguous for the deterministic and heuristic resolvers (e.g., the suffix match returned multiple candidates). The resulting `Relationship` will have a property indicating it was AI-generated (e.g., `properties: {'method': 'TIER_3_LLM'}`).

**`REFERENCES_SYMBOL`**
*   **Direction:** `(CodeEntity) -> [REFERENCES_SYMBOL] -> (CodeEntity or ExternalReference)`
*   **Purpose:** To capture "weaker" connections that aren't direct calls or inheritance. This is our solution for the C++ macro problem. It answers: "What other symbols does the `LOG` macro depend on?"
*   **Creation:** When the parser reports a reference from inside a macro body (e.g., from `LOG` to `fprintf`), the linking engine will attempt to resolve it. If it fails, it will create a link: `(LOG:MacroDefinition) -> [REFERENCES_SYMBOL] -> (fprintf:ExternalReference)`. This honestly represents the hidden dependency without claiming it's a direct call.

---

### **2. Foundational Architecture Principles**

#### **Pillar 1: The Principle of the Focused Expert (The Parser's Role)**

*   **What It Is:** Each parser is a "Sufficient Context Reporter." It is a master of a single language's syntax, and its **only job** is to analyze the Abstract Syntax Tree (AST) of a single file and report facts. It is a master of syntax, not cross-file semantics.

*   **The Context & Why It's Crucial:** We realized that trying to build linking logic (e.g., "what file does this `#include` point to?") inside every single parser would be a nightmare of duplicated, fragile, and language-specific code. It would make adding a new language a monumental task.

    Instead, we radically simplify the parser's role. It doesn't link; it **reports**. For every definition it finds, it yields a `CodeEntity`. For every reference it finds (a call, an inheritance, an import), it yields a rich, structured `RawSymbolReference` object. This report is its "dossier" on the reference, containing every contextual clue it can gather *from within that single file*.

*   **The Analogy:** The parser is an **expert witness at a crime scene**. It doesn't solve the case. It perfectly and factually reports: "I found these footprints, of this size, pointing in this direction. I also found these fingerprints on the doorknob."

#### **Pillar 2: The Principle of Centralized Intelligence (The Orchestrator's Role)**

*   **What It Is:** The Orchestrator is the single, universal "Deterministic Resolver." It is completely language-agnostic. Its only job is to take the standardized reports (`RawSymbolReference`) from any parser and apply a single, consistent set of rules to them.

*   **The Context & Why It's Crucial:** This solves the maintainability and consistency problem. All the "clever" linking logic lives in one place. This is a **Tier 1, Real-Time** resolver, meaning it only attempts to create links that can be resolved with **zero ambiguity** based on the context provided. For everything else, it creates a `PendingLink` "debt" node, honestly acknowledging what it doesn't know yet.

*   **The Analogy:** The Orchestrator is the **detective back at headquarters**. It receives the forensic reports from all the expert witnesses at all the different crime scenes. It is the only one with the "big picture" view (the live graph) and is responsible for connecting the dots.

#### **Pillar 3: The Principle of Provable Truth & Graceful Enrichment**

*   **What It Is:** This is the most important philosophical stance. The system will **never create a relationship it cannot prove.** A missing link is infinitely better than a wrong one. The graph must be trustworthy. This leads to a system that enriches itself over time as more proof becomes available.

*   **The Context & Why It's Crucial:** This principle solves the "race condition" and "expensive operation" problems that plagued our earlier designs.
    1.  **Provable Truth:** The Tier 1 resolver only makes high-confidence links. For everything else, it creates a `PendingLink` debt. The graph is always in a correct, if momentarily incomplete, state. It never lies.
    2.  **Graceful Enrichment:** The system autonomously "pays" these debts later. The **Linking Engine** is a set of asynchronous background workers that only run when the system is ready.
        *   **The Trigger is Quiescence:** The system knows it's "ready" by using an `IngestionHeartbeat` node. Only after a repository has stopped receiving new file updates for a configurable period (e.g., 60 seconds) are the more complex resolvers triggered.
        *   **The Tiers are Patient:** The Tier 2 (Deterministic) and Tier 3 (LLM) resolvers only operate on these "matured" debts, ensuring they have the most complete possible view of the graph.
    3.  **The Cache is the Memory:** The `ResolutionCache` ensures that once an expensive question is answered (especially by an LLM), it is never asked again.

*   **The Analogy:** The graph starts as a collection of accurate but disconnected **island chains** (the files). The Tier 1 resolver builds the bridges within each island chain. The Tier 2 and Tier 3 resolvers are the **ferry services** and **international airlines** that run on a schedule, patiently waiting to build the robust connections between the islands once they are fully mapped.

---

### **3. Data Contracts (`entities.py`): The Universal Language of the System**

#### **i. The Core Philosophy of Our Data Contracts**

This file is the most critical piece of the entire project. It is the **formal, typed contract** that defines how our disparate components—the Parsers, the Orchestrator, the Linking Engine, and the Graph Adapter—communicate. It is the single source of truth for the structure of our data.

The core principle behind these data models is to **separate factual reporting from interpretive resolution.** Parsers are "witnesses" that report facts (`CodeEntity`, `RawSymbolReference`). The Orchestrator and Linking Engine are "detectives" that interpret these facts to build the final graph, using `PendingLink` and `ResolutionCache` to manage the complex, asynchronous process of solving the case.

Every model and field in this file was designed through a rigorous process of debate and refinement to be as robust, clear, and universally applicable as possible, while making conscious, well-understood compromises.

---

#### **ii. The Core Graph Models: ID Structure and Metadata Philosophy**

This section defines the final structure of the core graph nodes. Our design philosophy is to **prioritize queryability and explicit data over opaque IDs.**

*   **The ID is a Unique Key:** The `id` field for every entity is a globally unique, human-readable string that serves as its primary key. It is designed for direct lookups and for establishing hierarchical context.
*   **Fields are for Querying:** Any data attribute that might be used to filter, sort, or find a group of nodes (e.g., `branch`, `start_line`, `commit_index`) **must** be stored as an explicit, typed field in the Pydantic model. This ensures the data can be properly indexed and efficiently queried by the graph database. We will **never** parse IDs to perform queries.
*   **The Orchestrator is the ID Authority:** The Orchestrator is solely responsible for constructing the final, composite ID strings, including any presentation logic like zero-padding numbers. The Pydantic models store the raw data.

---
**`Repository`**
*   **ID Format:** `"<repo_id>@<branch>"`
*   **Example ID:** `"automalar/web@main"`
*   **Key Fields:**
    *   `repo_id: str`: (e.g., `"automalar/web"`) - To query for all branches of a single repository.
    *   `branch: str`: (e.g., `"main"`) - To query for all repositories on a specific branch.

**`SourceFile`**
*   **ID Format:** `"<repository_id>|<relative_path>@<version_string>"`
    *   The `version_string` is `"<zero_padded_commit_index>-<zero_padded_local_save>"`.
*   **Example ID:** `"automalar/web@main|src/main.py@00234-432"`
*   **Key Fields:**
    *   `relative_path: str`: (e.g., `"src/main.py"`) - To query for all versions and branches of a single file.
    *   `commit_index: int`: (e.g., `234`) - Stored as a raw integer for efficient numerical queries.
    *   `local_save: int`: (e.g., `432`) - Stored as a raw integer for sorting and querying.
    *   `content_hash: str`: A SHA256 hash of the file content for idempotency.

---
*(This replaces the previous "TextChunk" and "CodeEntity" sections in the blueprint's "Core Graph Models" documentation)*

**`TextChunk`**
*   **ID Format:** `"<source_file_id>|<chunk_index>@<start_line>-<end_line>"`
*   **Example ID:** `"...|src/main.py@00234-432|0@1-12"`
*   **Rationale:**
    *   The `chunk_index` (`0`) ensures uniqueness within the file.
    *   Including the `@<start_line>-<end_line>` (`@1-12`) in the ID string provides immediate, human-readable context without needing to inspect the node's properties. It makes debugging and manual graph exploration much easier.
*   **Key Fields:**
    *   `start_line: int`: **(Critical)** Stored as a separate, indexed field for efficient range queries (e.g., "find the chunk containing line 42").
    *   `end_line: int`: **(Critical)** Same reason. We prioritize queryability.
    *   `chunk_content: str`: The raw text of the chunk.

**`CodeEntity`**
*   **ID Format:** `"<text_chunk_id>|<local_fqn>@<start_line>-<end_line>"`
*   **Example ID:** `"...|0@1-12|MyClass::my_method@9-11"`
*   **Rationale:**
    *   The `local_fqn` provides uniqueness within the chunk.
    *   Including the `@<start_line>-<end_line>` (`@9-11`) provides immediate, human-readable context for the location and span of the code entity.
*   **Key Fields:**
    *   `start_line: int`, `end_line: int`: **(Critical)** Stored as separate, indexed fields to enable features like "go to definition" and to quickly find all entities within a specific line range.
    *   `canonical_fqn: Optional[str]`: The parser's best-effort, language-specific canonical FQN. This is the primary key used for cross-file linking in the Tier 2 resolver.
    *   `type: str`: (e.g., `"ClassDefinition"`, `"MacroDefinition"`).
    *   `snippet_content: str`: The raw text of the entity's definition.

#### **iii. The Parser's Universal Report: `RawSymbolReference` and `ReferenceContext`**

These two models are the most critical part of the **"Sufficient Context Reporter"** philosophy. They are the standardized "forensic report" that every parser, regardless of language, must create. This is how we achieve a language-agnostic linking engine.

**The Core Idea:** Instead of yielding a simple `Relationship` with a string `target_id` (which is just a guess), the parser yields a `RawSymbolReference`. This object doesn't contain a guess; it contains **evidence**. It captures the literal text the developer wrote (`target_expression`) and, crucially, all the surrounding clues in a structured `ReferenceContext`.

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
    reference_type: str
    context: ReferenceContext
```

**Context and Rationale:**
*   **The Problem We Solved:** In earlier designs, we struggled with how a C++ parser and a Python parser could report imports in a way the Orchestrator could understand. A generic `dict` was proposed, but you correctly identified this as fragile and a source of "magic string" bugs.
*   **The Solution:** The `ReferenceContext` is a **strongly-typed, formal contract**. It forces every parser to speak the same language.
    *   A Python parser seeing `from .utils import helper` creates a `ReferenceContext(import_type=RELATIVE, path_parts=['.', 'utils'], ...)`
    *   A C++ parser seeing `#include <vector>` creates a `ReferenceContext(import_type=ABSOLUTE, path_parts=['vector'], ...)`
*   **The Benefit:** The Orchestrator's logic becomes simple and universal. It doesn't need `if language == 'python': ... elif language == 'cpp': ...`. It just looks at the `import_type` and knows exactly how to interpret the `path_parts`. This is the key to a maintainable, multi-language system.

---

#### **iv. The Linking Engine's State Machine: `PendingLink` and `ResolutionCache`**

These models are the "bookkeeping" tools that enable our **"Progressive Enrichment"** philosophy. They are the physical manifestation of our system's memory and its "to-do" list, allowing it to be autonomous, self-healing, and efficient.

```python
class LinkStatus(str, Enum):
    PENDING_RESOLUTION = "pending_resolution"
    READY_FOR_HEURISTICS = "ready_for_heuristics"
    AWAITING_TARGET = "awaiting_target" # For when an LLM provides a hint
    READY_FOR_LLM = "ready_for_llm"
    UNRESOLVABLE = "unresolvable"
    RESOLVED = "resolved"

class PendingLink(BaseModel):
    id: str # A deterministic hash of the linking question
    status: LinkStatus
    created_at: datetime
    reference_data: RawSymbolReference
    awaits_fqn: Optional[str] = None # The FQN hint provided by the LLM

class ResolutionCache(BaseModel):
    id: str # The same deterministic hash as the PendingLink
    resolved_target_id: str
    method: ResolutionMethod
```

**Context and Rationale:**

*   **The Problem We Solved:** How can a system handle links when the target file might not have been processed yet? And how can we avoid re-doing expensive LLM calls for the same problem?
*   **The Solution:**
    1.  **`PendingLink` (The "Debt"):** When the Orchestrator fails to make a high-confidence link during real-time ingestion, it doesn't give up. It creates a `PendingLink` node in the graph. This is our system's persistent "to-do" list. It's a promise that the system will try to resolve this link later.
    2.  **`LinkStatus` (The "Workflow Engine"):** This `Enum` is the state machine. It defines the exact lifecycle of a debt. A `PendingLink` is created as `PENDING_RESOLUTION`. The "Janitor" worker promotes it to `READY_FOR_HEURISTICS`. The "Heuristic Resolver" might solve it, or promote it to `READY_FOR_LLM`. This explicit status field is what allows our different background workers to coordinate without interfering with each other. It is far more robust than a simple boolean flag or magic strings. The addition of `AWAITING_TARGET` was a critical insight to handle the case where the LLM provides a hint for a target that doesn't exist *yet*.
    3.  **`ResolutionCache` (The "Memory"):** This is our solution to the "wasted LLM call" problem. An LLM call is the most expensive operation in our system. When the LLM successfully provides an answer for a `PendingLink`, we store that answer in a `ResolutionCache` node. The `id` of the cache node is a deterministic hash of the original question, just like the `PendingLink`'s id. The next time the LLM worker picks up a similar debt, it will **check the cache first**. If an answer exists, it uses it for free, avoiding a redundant API call.

This state machine, implemented as queryable nodes in the graph, is what allows our system to be both **eventually consistent** and **fiscally responsible**.

---

## **4. System Components**

### **Component A: The Parser - The "Sufficient Context Reporter"**

#### **Core Philosophy**

The single most important architectural decision we made was to redefine the parser's job. In earlier, flawed designs, the parser was a "Reporter and Guesser." It tried to find code and then guess at the relationships between them. This made the parser fragile, complex, and difficult to maintain, especially in a multi-language environment.

The new philosophy is that the parser is a **Focused Expert Reporter.** Its responsibility is to be the world's leading expert on the syntax of a single file for a single language. It makes **zero assumptions** about any other file, repository, or the state of the graph. It is a stateless, pure function that transforms source code text into a stream of high-fidelity, factual data.

Its contract is to yield only two types of objects:
1.  **`CodeEntity`:** A factual report of a code structure that has been *defined* in this file.
2.  **`RawSymbolReference`:** A factual report of a *reference* to another symbol, bundled with all the contextual clues the parser can gather from its immediate surroundings.

Crucially, **it never yields `Relationship` objects.** The parser does not link; it only provides the evidence needed for a separate component (the Orchestrator) to do the linking.

#### **Parser Responsibilities**

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

#### **Known Limitations and Conscious Compromises**

We have made several conscious trade-offs to prioritize simplicity, speed, and language-agnosticism over perfect, compiler-level accuracy.

*   **Compiled Languages:** This is the most significant compromise. The parser operates on the code **as written**, not as compiled. For cpp as example:
    *   **What IS Covered:** We will create `CodeEntity` nodes for `MacroDefinition` and `RawSymbolReference` nodes for `MACRO_CALL`. We can even find symbol references *inside* simple macro bodies (`REFERENCES_SYMBOL`). This provides immense value.
    *   **What is NOT Covered:** Conditional compilation (`#ifdef`) and token-pasting (`##`). The graph will represent all possible code paths from `#ifdef` blocks, and it will not understand symbols generated by token-pasting. We have decided that requiring a pre-processing step is an unacceptable burden.

*   **File-Local FQN Generation:** The parser's `_get_fqn_for_node` is a powerful heuristic, not a perfect algorithm.
    *   **What IS Covered:** It will correctly identify namespaces and parent classes for the vast majority of standard code structures.
    *   **What is NOT Covered:** It will be tricked by complex uses of `using namespace` and advanced C++ features like Argument-Dependent Lookup (ADL). The generated FQN is a high-fidelity "local name," not a guaranteed "canonical name." This is an acceptable trade-off to avoid the complexity of a stateful, multi-file parser.

*   **Wildcard Imports:** For languages like Python, we explicitly do not support resolving symbols from wildcard imports (`from .utils import *`). The parser cannot provide sufficient context, and our core principle is to **never guess**. The parser will simply not yield a `RawSymbolReference` for calls to symbols imported this way.

---

### **Component B: The Orchestrator - The "Tier 1 Real-Time Resolver"**

#### **Core Philosophy**

The Orchestrator's philosophy is one of **Speed, Safety, and Honesty.** It operates under a strict set of rules designed to ensure that the graph is always in a consistent state and that every action taken is based on high-confidence, provable information.

*   **Speed:** It is designed to be the fast, real-time part of the system. Its job is to process a single file as quickly as possible. To achieve this, it **defers** any complex or ambiguous linking tasks. It does the "easy" work now and leaves the "hard" work for the asynchronous workers.
*   **Safety (Atomicity):** Its primary job is to process a `FileProcessingRequest` **atomically**. This means the entire operation--from deleting old versions to adding new nodes and creating links--is wrapped in a single database transaction. If any part of the process fails (e.g., a parser error, a bug in the Orchestrator), the entire transaction is rolled back. The graph is never left in a broken, half-updated state. This is a non-negotiable guarantee.
*   **Honesty (Tier 1 Resolution):** The Orchestrator is a **High-Confidence, Low-Ambiguity** resolver. It will only attempt to create a final `Relationship` if the context provided by the parser is so clear that the link is effectively proven (e.g., a direct relative import). For every other reference, it honestly admits, "I do not have enough information to resolve this with 100% certainty right now." Instead of guessing or failing, it creates a `PendingLink` "debt" node, which is a factual statement of an unresolved dependency.

#### **Orchestrator Workflow**

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
*   **Rationale:** This ensures that the entire state change--new nodes, new high-confidence links, and new "debt" nodes--is saved to the graph in a single, atomic operation.

#### **Orchestrator Boundaries**

*   **It does NOT perform complex, graph-wide queries.** The Tier 1 resolver only looks for targets in a very specific, limited scope. All broad searches (like suffix matching FQNs) are the responsibility of the Tier 2 worker.
*   **It does NOT call the LLM.** This is a critical boundary. The real-time ingestion path must be fast and deterministic.
*   **It does NOT know about other files in a "batch."** Its logic is entirely focused on the single `FileProcessingRequest` it was given, making it simple, stateless, and easy to test.

---

### **Component C: The Linking Engine - The Asynchronous Workers**

#### **Core Philosophy**

The Linking Engine's philosophy is to **never interfere with real-time ingestion**. Its job is to work patiently in the background, cleaning up the "debt" (`PendingLink` nodes) left by the fast-moving Orchestrator. It solves the fundamental race condition problem--"how do I resolve a link when the target might not exist yet?"--by simply **waiting until the initial "ingestion storm" is over.**

This is a tiered system where each tier operates on a different level of confidence and has a different trigger, ensuring that expensive or complex operations are only performed when it's safe and efficient to do so.

#### **Component C1: The "Janitor" - The Quiescence Trigger**

##### **Core Philosophy**

The philosophy of the Janitor is **"Patient, Non-Intrusive Observation."**

Its job is not to be "smart." Its job is to be a simple, reliable, and low-impact background process that answers one critical question: **"Has the 'ingestion storm' for a given repository branch passed?"**

*   **Patient:** It does not try to predict the end of an ingestion session. It simply waits for a pre-defined period of inactivity (quiescence). This is a robust, time-tested pattern for handling bursty, asynchronous event streams.
*   **Non-Intrusive:** It never modifies the core code graph (`CodeEntity`, `Relationship`, etc.). Its only job is to observe the `IngestionHeartbeat` nodes and update the `status` of `PendingLink` nodes. It acts as a "promoter," moving work from one queue to another.
*   **Observer:** It is the only component that uses time as a trigger. This is a conscious architectural decision. We have isolated the system's only time-based logic into this single, simple component, making the rest of the system purely event-driven and deterministic.

##### **Janitor Workflow**

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

##### **Janitor Rationale and Trade-offs**

*   **What this Solves:** This is the most robust, non-invasive way to solve the "when is the ingestion session over?" problem. It does not require a complex external job scheduler or stateful orchestration logic. The state is stored and managed entirely within the graph itself.
*   **The Trade-off (Latency):** The primary compromise is a built-in delay. A link that requires Tier 2 resolution will not be created instantly. It will only be created after the `QUIESCENCE_PERIOD_SECONDS` has elapsed *and* the Janitor and Heuristic Resolver workers have run. For most use cases, a delay of 1-2 minutes for complex, graph-wide linking is a very acceptable price to pay for correctness and architectural simplicity.
*   **The Robustness:** This system is highly robust to failure. If the Janitor worker crashes, it will simply restart on its next scheduled run and pick up where it left off by querying the graph for active heartbeats. No state is lost. If a file is updated during the quiescent period, its `process_single_file` call will simply flip the heartbeat's status back to `active`, correctly and automatically pausing any further Tier 2 resolution until the system goes quiet again.

#### **Component C2: The "Heuristic & Deterministic Resolver" (Tier 2)**

##### **Core Philosophy**

The philosophy of this component is **"Certainty First, Intelligent Heuristics Second."**

This worker runs *after* an ingestion session is quiescent, giving it a complete and stable "worldview" of the repository. Its primary job is to resolve the vast majority of `PendingLink` debts left by the real-time Tier 1 resolver. It will first attempt to find links with 100% certainty via direct lookups. If those fail, it will then apply a powerful, but safe, heuristic (the "Verified Suffix Match") to solve more complex cases, like C++ `using namespace` ambiguities. Its guiding principle is to **maximize deterministic resolution without ever sacrificing accuracy.**

##### **Tier 2 Workflow**

**1. The Trigger:**
*   This worker is a simple, stateless background process that polls the graph for `PendingLink` nodes with `status: 'ready_for_heuristics'`. This status is set by the `Janitor` worker after a repository has gone quiescent.

**2. The Prioritized Resolution Chain:**
*   For each `PendingLink` it finds, it executes a prioritized chain of queries. It stops at the first step that produces a single, verified result. If any step produces multiple results, it promotes the link to the LLM tier with the found candidates as context.

**The Code Logic (Inside the Tier 2 Worker):**

```python
# A conceptual function inside the Tier 2 worker
async def run_tier2_resolution_for_link(tx, pending_link: PendingLink):
    # --- Attempt 1: High-Confidence External Link (by import_id) ---
    target_id = await resolve_external_link_by_import_id(tx, pending_link)
    if target_id:
        await create_final_link(tx, pending_link, target_id, ResolutionMethod.HEURISTIC_MATCH)
        return

    # --- Attempt 2: High-Confidence Internal Link (by Exact FQN Match) ---
    target_id = await resolve_internal_link_by_exact_fqn(tx, pending_link)
    if target_id:
        await create_final_link(tx, pending_link, target_id, ResolutionMethod.HEURISTIC_MATCH)
        return

    # --- Attempt 3: The Verified Suffix Match Heuristic ---
    candidate_ids = await resolve_internal_link_by_fqn_suffix(tx, pending_link)

    if len(candidate_ids) == 1:
        # The heuristic found exactly one unambiguous match. This is a success.
        await create_final_link(tx, pending_link, candidate_ids[0], ResolutionMethod.HEURISTIC_MATCH)
        return

    # --- If all attempts fail or result in ambiguity, promote to Tier 3 ---
    await promote_link_for_llm(tx, pending_link, candidates=candidate_ids)
```

**Resolution Helper Functions:**

*   **`resolve_external_link_by_import_id`:** Solves links like `import pandas`. It looks for a `Repository` node with a matching `provides_import_id` hint and then searches within that repository for the target `CodeEntity`. Fails if not exactly one match is found.
*   **`resolve_internal_link_by_exact_fqn`:** Solves links where the full name is known. It performs an exact-match query for a `CodeEntity` with a matching `canonical_fqn` within the same repository. Fails if not exactly one match is found.
*   **`resolve_internal_link_by_fqn_suffix`:** Solves links where a partial name is used (e.g., C++ `using namespace`). It performs a suffix-based search (e.g., `LIKE '%::MyClass'`) against the `canonical_fqn` field of all `CodeEntity` nodes in the repository. It returns a list of all matching candidate IDs.

**Final Action Functions:**

*   **`create_final_link`:** Called on success. Creates the final `Relationship`, creates a `ResolutionCache` entry for the answer, and deletes the `PendingLink` debt.
*   **`promote_link_for_llm`:** Called on failure or ambiguity. Updates the `PendingLink` status to `READY_FOR_LLM`, attaching any found candidates to enrich the prompt for the Tier 3 worker.

##### **Tier 2 Rationale and Trade-offs**

This Tier 2 design finds the optimal balance between accuracy and completeness.

*   **What it Covers:** It handles the most common high-confidence links (direct and external) and now also intelligently resolves more complex cases like C++ `using namespace` ambiguities.
*   **The "Slow Query" Trade-off:** The suffix match heuristic can be slower than a direct lookup. This is an **acceptable trade-off** because this query runs asynchronously in a background worker and does not block real-time ingestion. We pay a small price in background processing time for a significant increase in deterministic linking.
*   **The "Ambiguity" Feature:** When the suffix match finds multiple valid candidates, the system correctly identifies this as a "hard problem" and escalates it. It provides the LLM with a pre-vetted list of options, making the LLM's job easier and its answer more reliable. This is a feature, not a bug.

#### **Component C3: The "LLM Consultant" and "Repair" Subsystem**

This is the final and most advanced part of our linking engine. It's designed to be **patient, efficient, and event-driven**. Its primary job is not just to call an LLM, but to intelligently manage the entire lifecycle of a "hard problem."

This subsystem is composed of two distinct workers that act on specific graph states.

##### **Component C3A: The "LLM Consultant" Worker (The Question Asker)**

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

##### **Component C3B: The "Repair Worker" (The Link-Maker)**

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

#### **D. The Graph Utilities (`graph_utils.py`) - The Specialized Toolkit**

*   **i. The Core Philosophy:**
    The philosophy of this module is **Abstraction and Encapsulation**. The rest of our parser library—including the Orchestrator and all Parsers—should not know or care about the specific implementation details of the `cognee` graph database. This module acts as a clean, internal API layer that translates our system's high-level intentions (e.g., "delete this file's data") into the precise, low-level function calls required by the `cognee` graph adapter.

*   **ii. Key Responsibilities:**
    *   **Encapsulate all `cognee` imports:** This is the **only** module in our core library (besides the `cognee_adapter.py`) that will have `from cognee... import ...`. **The `parsers` and `orchestrator` must remain pure and have no knowledge of `cognee`'s internal models.**
    *   **Provide a Stable Internal API:** It exposes a set of simple, intent-based functions like `find_nodes_with_filter` and `save_graph_data`.
    *   **Handle Database-Specific Logic:** It contains the logic for constructing the `filter_dict` arguments and handling the responses from the `cognee` adapter.

---

#### **E. The Cognee Adapter (`cognee_adapter.py`) - The Shipping Department**

*   **i. The Core Philosophy:**
    The philosophy of the adapter is **Decoupling and Translation**. It is a pure, stateless function that acts as the one and only bridge between our internal data models (`entities.py`) and the specific `Node` and `Edge` objects required by the `cognee` graph engine.

*   **ii. Key Responsibilities:**
    1.  **Translate Nodes:** It takes our Pydantic models (`CodeEntity`, `PendingLink`, etc.) and converts each one into a `cognee.Node` object.
    2.  **Translate Edges:** It takes our `Relationship` model (which uses our string IDs) and converts it into the `(source_id, target_id, type, {props})` tuple format that `graph_utils` expects.
    3.  **Populate Metadata:** It correctly dumps our Pydantic model's data into the `attributes` dictionary of the `cognee.Node`, ensuring all our valuable context is preserved in the graph.

---

#### **F. The Utility Modules (`chunking.py` & `utils.py`)**

*   **`chunking.py`:** A **Pure Function**. It takes file content and slice points and returns a list of `TextChunk` objects. It has no side effects and no knowledge of the rest of the system. **Your existing code for this is perfect and needs no changes.**
*   **`utils.py`:** **Shared, Stateless Toolbox**. It contains generic helper functions (`read_file_content`, `get_node_text`, `parse_temp_code_entity_id`) that have no dependencies on any other part of our system. **Your existing code for this is perfect and needs no changes.**

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
