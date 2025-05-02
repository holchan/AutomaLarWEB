# Define Tree-sitter queries for C++
CPP_QUERIES = {
    "includes": """
        (preproc_include path: [(string_literal) (system_lib_string)] @include) @include_statement
        """,
    "functions": """
        (function_definition
            declarator: [
                (function_declarator declarator: (identifier) @name) ;; Standard function
                (function_declarator declarator: (field_identifier) @name) ;; Member function
                (function_declarator declarator: (operator_name) @name) ;; Operator overload
                (destructor_name) @name ;; Destructor name
            ]
        ) @definition
        """,
    "classes": """
        (class_specifier name: [(type_identifier) (identifier)] @name) @definition
        """,
    "structs": """
        (struct_specifier name: [(type_identifier) (identifier)] @name) @definition
        """,
    # --- CORRECTED NAMESPACE QUERY ---
    "namespaces": """
        (namespace_definition name: (identifier) @name) @definition
        ;; Note: Nested namespaces might require additional handling or a different query if just 'identifier' isn't enough.
        """,
    # --- CORRECTED ENUM QUERY ---
    "enums": """
        [
         (enum_specifier name: [(type_identifier) (identifier)] @name) @definition ;; Normal enum
         (enum_specifier class name: [(type_identifier) (identifier)] @name) @definition ;; Enum class
        ]
        """,
    "typedefs": """
        (type_definition type: (_) declarator: [(type_identifier)(identifier)] @name) @definition
        """,
    "using": """
        (using_declaration) @using_statement
        """
    # Add using namespace directive capture if needed:
    # "using_namespace": """
    #     (namespace_alias_definition name: (identifier) @name) @using_statement ;; using ns = std;
    #     (using_declaration "namespace" [(identifier)(nested_namespace_specifier)] @name) @using_statement ;; using namespace std; - needs grammar check
    # """
}

class CppParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries = {}
        if self.language:
            logger.info("Attempting to compile C++ queries one by one...") # Changed log
            failed_queries = []
            for name, query_str in CPP_QUERIES.items():
                # print(f"DEBUG: Compiling C++ query: {name}") # Keep for debugging if needed
                try:
                    self.queries[name] = self.language.query(query_str)
                    logger.debug(f"Successfully compiled C++ query: {name}")
                    # print(f"DEBUG: Successfully compiled C++ query: {name}") # Keep for debugging
                except Exception as e:
                    logger.error(f"Failed to compile C++ query '{name}': {e}", exc_info=True)
                    # print(f"DEBUG: FAILED to compile C++ query '{name}': {e}") # Keep for debugging
                    failed_queries.append(name)

            if not failed_queries:
                logger.info("Successfully compiled ALL C++ queries.")
            else:
                logger.error(f"Failed to compile the following C++ queries: {', '.join(failed_queries)}. C++ parsing will be limited.")
                # --- IMPORTANT: Clear queries ONLY if errors make parsing impossible ---
                # Decide based on which queries failed. If core queries fail, clear.
                # If only minor ones fail, maybe allow proceeding with limited parsing.
                # For now, let's clear if *any* fail, as the tests expect specific entities.
                self.queries = {} # Clear queries if ANY failed
        else:
            logger.error("C++ tree-sitter language not loaded. C++ parsing will be limited.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]: # Use BaseModel hint
        # -- This guard clause prevents execution if queries failed compilation --
        if not self.parser or not self.language or not self.queries:
            logger.error(f"C++ parser not available or core queries failed compilation, skipping parsing for {file_path}")
            # Optional: Yield basic chunks even if detailed parsing fails
            # content_fallback = await read_file_content(file_path)
            # if content_fallback:
            #    for i, chunk_text in enumerate(basic_chunker(content_fallback)):
            #        if chunk_text.strip(): yield TextChunk(f"{file_id}:chunk:{i}", file_id, chunk_text, i)
            return # Exit if queries aren't ready

        content = await read_file_content(file_path)
        if content is None:
            logger.error(f"Could not read content from {file_path}")
            return

        try:
            content_bytes = bytes(content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node

            # 1. Yield Chunks
            chunks = basic_chunker(content)
            for i, chunk_text in enumerate(chunks):
                if not chunk_text.strip(): continue
                chunk_id_str = f"{file_id}:chunk:{i}"
                yield TextChunk(chunk_id_str=chunk_id_str, parent_id=file_id, text=chunk_text, chunk_index=i)

            # 2. Yield Code Entities (Functions, Classes, Structs, Namespaces, Enums, Typedefs)
            entity_configs = [
                ("functions", "FunctionDefinition"),
                ("classes", "ClassDefinition"),
                ("structs", "StructDefinition"),
                ("namespaces", "NamespaceDefinition"),
                ("enums", "EnumDefinition"),
                ("typedefs", "TypeDefinition"),
            ]

            for query_name, entity_class_name in entity_configs:
                if query_name in self.queries:
                    query = self.queries[query_name]
                    logger.debug(f"Executing C++ query '{query_name}' for {file_path}")
                    # Use query.matches() for safer capture handling
                    for match_id, captures_in_match in query.matches(root_node):
                        definition_node: Optional[TSNODE_TYPE] = None
                        name_node: Optional[TSNODE_TYPE] = None

                        for capture_name, node in captures_in_match:
                            if capture_name == "definition":
                                definition_node = node
                            elif capture_name == "name":
                                name_node = node
                            # Break early if we found both for efficiency? Optional.

                        if definition_node and name_node:
                            name = get_node_text(name_node, content_bytes)
                            entity_text = get_node_text(definition_node, content_bytes)
                            start_line = definition_node.start_point[0] + 1
                            end_line = definition_node.end_point[0] + 1

                            if name and entity_text:
                                entity_id_str = f"{file_id}:{entity_class_name}:{name}:{start_line}"
                                logger.debug(f"Yielding C++ CodeEntity: {entity_class_name} - {name}")
                                yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                            else:
                                 logger.warning(f"Could not extract name or text for C++ {entity_class_name} at {file_path}:{start_line}")
                        # Log if a definition was found but name wasn't captured in the same match
                        elif definition_node and not name_node:
                            logger.warning(f"Found C++ {entity_class_name} definition node but no name node in match at {file_path}:{definition_node.start_point[0]+1}")


            # 3. Yield Dependencies (Includes, Using)
            processed_statements = set() # Use start line to avoid duplicates

            # Includes
            if "includes" in self.queries:
                include_query = self.queries["includes"]
                logger.debug(f"Executing C++ query 'includes' for {file_path}")
                for match_id, captures_in_match in include_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = None
                    include_node: Optional[TSNODE_TYPE] = None
                    for capture_name, node in captures_in_match:
                        if capture_name == "include_statement": statement_node = node
                        elif capture_name == "include": include_node = node

                    if statement_node and include_node:
                        start_line = statement_node.start_point[0] + 1
                        if start_line in processed_statements: continue

                        target = get_node_text(include_node, content_bytes)
                        if target and target.startswith(('"', '<')): target = target[1:-1] # Clean quotes/brackets
                        snippet = get_node_text(statement_node, content_bytes)
                        end_line = statement_node.end_point[0] + 1

                        if target and snippet:
                            dep_id_str = f"{file_id}:dep:include:{target}:{start_line}"
                            logger.debug(f"Yielding C++ Include Dependency: {target}")
                            yield Dependency(dep_id_str, file_id, target, snippet, start_line, end_line)
                            processed_statements.add(start_line)
                        else:
                            logger.warning(f"Could not extract target or snippet for C++ include at {file_path}:{start_line}")

            # Using directives (add logic if query exists and is compiled)
            if "using" in self.queries:
                 using_query = self.queries["using"]
                 logger.debug(f"Executing C++ query 'using' for {file_path}")
                 for match_id, captures_in_match in using_query.matches(root_node):
                     using_statement_node: Optional[TSNODE_TYPE] = None
                     # Extract target name based on specific captures in the 'using' query if defined
                     # e.g., capture @name for 'using namespace std;' or 'using MyType = int;'
                     # For simplicity, let's assume the query @using_statement captures the whole line
                     target_name = "using_directive" # Placeholder if name isn't captured
                     for capture_name, node in captures_in_match:
                         if capture_name == "using_statement": using_statement_node = node
                         # Add elif capture_name == "name": target_name = get_node_text(...)

                     if using_statement_node:
                         start_line = using_statement_node.start_point[0] + 1
                         if start_line in processed_statements: continue

                         snippet = get_node_text(using_statement_node, content_bytes)
                         end_line = using_statement_node.end_point[0] + 1

                         # Determine target (this is tricky without a good query capture)
                         # Maybe extract from snippet?
                         if snippet and "using namespace" in snippet:
                            target_name = snippet.split("namespace")[-1].strip().rstrip(';')
                         elif snippet and "=" in snippet: # using alias = type;
                             target_name = snippet.split('=')[0].replace("using",'').strip()


                         if snippet:
                             dep_id_str = f"{file_id}:dep:using:{target_name}:{start_line}"
                             logger.debug(f"Yielding C++ Using Dependency: {target_name}")
                             # Using target_name for target_module, adjust if needed
                             yield Dependency(dep_id_str, file_id, target_name, snippet, start_line, end_line)
                             processed_statements.add(start_line)
                         else:
                             logger.warning(f"Could not extract snippet for C++ using directive at {file_path}:{start_line}")

        except Exception as e:
            logger.error(f"Failed to parse C++ file {file_path}: {e}", exc_info=True)
