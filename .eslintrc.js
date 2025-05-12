module.exports = {
  root: true,

  parser: '@typescript-eslint/parser',

  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: {
      jsx: true,
    },
    tsconfigRootDir: __dirname,
    project: ['./tsconfig.json'],
  },

  settings: {
    react: {
      version: 'detect',
    },
  },

  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
    'plugin:jsx-a11y/recommended',
    'plugin:import/errors',
    'plugin:import/warnings',
    'plugin:import/typescript',
    'plugin:@typescript-eslint/recommended',
    'prettier',
  ],

  plugins: [
    'react',
    'react-hooks',
    'jsx-a11y',
    'import',
    '@typescript-eslint',
  ],

  rules: {
    // Place project-specific ESLint rules overrides here.
    // Example: Allow console logs in development builds
    // 'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',

    // Example: Custom rule severity
    // 'no-unused-vars': 'warn',

    // Override recommended rules if needed
    // 'react/react-in-jsx-scope': 'off', // Not needed for Next.js 13+
    // '@typescript-eslint/explicit-function-return-type': 'off', // Often too strict

    // Add or override rules from plugins
    // 'import/order': 'warn',

    'prettier/prettier': 'warn',
  },
  overrides: [
    {
      files: ['**/*.ts', '**/*.tsx'],
      rules: {
      },
    },
    {
      files: ['**/__tests__/**/*.[jt]s?(x)', '**/?(*.)+(spec|test).[jt]s?(x)'],
      extends: ['plugin:jest/recommended'],
    },
  ],
};
