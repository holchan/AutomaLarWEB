/docs
├── 00_PROJECT_FOUNDATION/
│   ├── 00_AUTOMALAR_INTRO.mdx         # Core purpose and goals, statements
│   ├── 01_BRAND_IDENTITY.mdx          # Voice, tone, messaging
│   └── 02_AUTOMALAR_FEATURES.mdx      # What is AUTOMALAR, what it has to offer
│
├── 01_WEBSITE_ARCHITECTURE/
│   ├── 00_SITEMAP.mdx                 # Page hierarchy and navigation flow
│   ├── 01_WEBSITE_TEMPLATE.mdx        # Overall look of the site, main blocks and broad idea
│   ├── 02_USER_FLOWS.mdx              # Key user journeys through the site
│   ├── 03_RESPONSIVE_STRATEGY.mdx     # Approach to different devices
│   ├── 04_PERFORMANCE_TARGETS.mdx     # Loading times and optimization goals
│   ├── 05_ERROR_HANDLING_STRATEGY.mdx # How errors will be displayed and managed
│   └── 06_SEO_STRATEGY.mdx            # SEO approach and implementation
│
├── 02_VISUAL_DESIGN/
│   ├── 00_DESIGN_SYSTEM.mdx           # Colors, typography, spacing, etc.
│   ├── 01_COMPONENT_LIBRARY.mdx       # UI components and patterns
│   ├── 02_LAYOUT_GRID.mdx             # Spacing and alignment system
│   ├── 03_ICONOGRAPHY.mdx             # Custom icons and usage
│   ├── 04_IMAGERY_GUIDELINES.mdx      # Photo style and treatment
│   ├── 05_DARK_MODE_SPECS.mdx         # Dark theme implementation
│   ├── 06_MICRO_INTERACTIONS.mdx      # Small animations and feedback
│   ├── 07_SCROLL_EFFECTS.mdx          # Parallax and scroll-triggered animations
│   └── 08_INTERACTIVE_DIAGRAMS.mdx    # Explorable product features
│
├── 03_PAGE_SPECIFICATIONS/
│   ├── 00_LANDING_PAGE.mdx            # Hero, value prop, CTAs
│   ├── 01_AUXILIAR_SECONDARY_PAGES.mdx # Planning and laying the fillers/secondary pages on the frontpage
│   ├── 02_CENTRAL_CONSOLE_MODULE_PAGE.mdx # Interactive presentation of main control panel
│   ├── 03_CEILING_MODULE_PAGE.mdx     # Exploded view and features
│   ├── 04_LIGHT_SWITCH_MODULE.mdx     # Smart lighting controls showcase
│   ├── 05_LOGIN_PAGE.mdx              # Authentication experience
│   ├── 06_USER_DASHBOARD.mdx          # Customer portal post-login
│   ├── 07_CHAT_PAGE.mdx               # AI chat experience interface
│   ├── 08_BLOG_PAGE.mdx               # Blog listing and article pages
│   ├── 09_ABOUT_US.mdx                # Company story and team
│   └── 10_CONTACT_PAGE.mdx            # Contact methods and form
│
├── 04_ART_WORKSHOP/
│   ├── 00_HERO_SCENE_SCREENPLAY.mdx   # 3D asset specifications
│   └── 01_3D_MODULES_PRESENTATION.mdx # Motion principles and timing
│
├── 05_TECHNICAL_IMPLEMENTATION/
│   ├── 00_TECH_STACK.mdx              # Framework and library choices
│   ├── 01_FRONTEND_ARCHITECTURE.mdx   # Component structure and state management
│   ├── 02_DATABASE_INTEGRATION/
│   │   ├── 00_DATABASE_OVERVIEW.mdx   # Database selection and architecture
│   │   ├── 01_SCHEMA_DESIGN.mdx       # Data models and relationships
│   │   ├── 02_PRISMA_SETUP.mdx        # ORM configuration and usage
│   │   └── 03_DATA_MIGRATION.mdx      # Handling schema changes
│   ├── 03_STATE_MANAGEMENT/
│   │   ├── 00_OVERVIEW.mdx            # General approach to state management
│   │   ├── 01_GLOBAL_STATE.mdx        # Global state implementation (Context, Redux, etc.)
│   │   ├── 02_LOCAL_STATE.mdx         # Component-level state strategies
│   │   └── 03_SERVER_STATE.mdx        # Handling server data (React Query, SWR)
│   ├── 04_ROUTING/
│   │   ├── 00_ROUTING_STRATEGY.mdx    # Next.js routing approach
│   │   ├── 01_DYNAMIC_ROUTES.mdx      # Implementation of dynamic routes
│   │   └── 02_NAVIGATION.mdx          # Navigation components and patterns
│   ├── 05_API_INTEGRATION/
│   │   ├── 00_API_ARCHITECTURE.mdx    # Overall API strategy
│   │   ├── 01_AUTHENTICATION_API.mdx  # Auth endpoints and integration
│   │   ├── 02_USER_DATA_API.mdx       # User data handling
│   │   └── 03_CHAT_API.mdx            # Integration with AI chat service
│   ├── 06_3D_IMPLEMENTATION/
│   │   ├── 00_THREE_JS_SETUP.mdx      # Basic Three.js configuration
│   │   ├── 01_MODEL_LOADING.mdx       # Loading and optimizing 3D models
│   │   ├── 02_ANIMATIONS.mdx          # 3D animation implementation
│   │   ├── 03_INTERACTIONS.mdx        # User interactions with 3D elements
│   │   └── 04_PERFORMANCE.mdx         # Optimizing 3D performance
│   ├── 07_ERROR_HANDLING/
│   │   ├── 00_ERROR_TYPES.mdx         # Categorization of possible errors
│   │   ├── 01_CLIENT_SIDE_ERRORS.mdx  # Handling frontend errors
│   │   ├── 02_SERVER_SIDE_ERRORS.mdx  # Handling backend errors
│   │   ├── 03_AI_SERVICE_ERRORS.mdx   # Handling AI-specific failures
│   │   └── 04_ERROR_REPORTING.mdx     # Logging and monitoring errors
│   ├── 08_AUTHENTICATION/
│   │   ├── 00_AUTH_STRATEGY.mdx       # Overall authentication approach
│   │   ├── 01_USER_SESSIONS.mdx       # Session management
│   │   └── 02_PROTECTED_ROUTES.mdx    # Implementing route protection
│   ├── 09_INTERNATIONALIZATION/
│   │   ├── 00_I18N_STRATEGY.mdx       # Approach to multi-language support
│   │   ├── 01_TRANSLATION_WORKFLOW.mdx # Managing translation content
│   │   └── 02_LANGUAGE_SWITCHING.mdx  # UI for changing languages
│   ├── 10_CONTENT_MANAGEMENT/
│   │   ├── 00_BLOG_SYSTEM.mdx         # Blog content architecture
│   │   ├── 01_MDX_INTEGRATION.mdx     # Using MDX for rich content
│   │   └── 02_CONTENT_WORKFLOW.mdx    # Process for creating and publishing content
│   ├── 11_RESPONSIVE_IMPLEMENTATION.mdx # Breakpoints and adaptation
│   ├── 12_PERFORMANCE_OPTIMIZATION/
│   │   ├── 00_LOADING_STRATEGY.mdx    # Initial loading and code splitting
│   │   ├── 01_IMAGE_OPTIMIZATION.mdx  # Image loading and optimization
│   │   ├── 02_FONT_LOADING.mdx        # Font loading strategies
│   │   └── 03_METRICS_MONITORING.mdx  # Performance metrics and monitoring
│   └── 13_ANALYTICS_SETUP.mdx         # User behavior tracking
│
├── 06_WORKFLOW/
│   ├── 00_DEVELOPMENT_ENVIRONMENT/
│   │   ├── 00_LOCAL_SETUP.mdx         # Setting up local development
│   │   ├── 01_ENV_VARIABLES.mdx       # Environment variables management
│   │   └── 02_EDITOR_CONFIG.mdx       # Editor settings and extensions
│   ├── 01_GIT_WORKFLOW/
│   │   ├── 00_BRANCHING_STRATEGY.mdx  # Git branching approach
│   │   └── 01_COMMIT_CONVENTIONS.mdx  # Commit message standards
│   ├── 02_CI_CD_PIPELINE/
│   │   ├── 00_PIPELINE_OVERVIEW.mdx   # CI/CD architecture
│   │   ├── 01_BUILD_PROCESS.mdx       # Build configuration
│   │   ├── 02_TESTING_AUTOMATION.mdx  # Automated testing in CI
│   │   └── 03_DEPLOYMENT_AUTOMATION.mdx # Automated deployment
│   ├── 03_TESTING_STRATEGY/
│   │   ├── 00_TESTING_OVERVIEW.mdx    # Testing philosophy and approach
│   │   ├── 01_UNIT_TESTING.mdx        # Component and function testing
│   │   ├── 02_INTEGRATION_TESTING.mdx # Testing component interactions
│   │   ├── 03_E2E_TESTING.mdx         # End-to-end testing
│   │   └── 04_VISUAL_TESTING.mdx      # Visual regression testing
│   ├── 04_CODE_QUALITY/
│   │   ├── 00_LINTING.mdx             # ESLint configuration
│   │   ├── 01_FORMATTING.mdx          # Prettier setup
│   │   ├── 02_TYPE_CHECKING.mdx       # TypeScript configuration
│   │   └── 03_PRE_COMMIT_HOOKS.mdx    # Husky and lint-staged setup
│   └── 05_DEPLOYMENT_PROCESS/
│       ├── 00_ENVIRONMENTS.mdx        # Development, staging, production
│       ├── 01_DEPLOYMENT_STRATEGY.mdx # Deployment approach
│       ├── 02_ROLLBACK_PROCEDURES.mdx # Handling failed deployments
│       └── 03_MONITORING.mdx          # Post-deployment monitoring
│
└── 07_PROJECT_MEMORY/
    ├── DECISION_LOG/
    │   ├── YYYY-MM-DD_DECISION_TITLE.mdx
    │   └── README.mdx
    ├── DEV_DIARY/
    │   ├── YYYY-MM-DD_ENTRY_TITLE.mdx
    │   └── README.mdx
    └── COMMIT_HISTORY/
        ├── YYYY-MM-DD_COMMIT_SUMMARY.mdx
        └── README.mdx
