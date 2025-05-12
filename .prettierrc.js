module.exports = {
  printWidth: 100,
  tabWidth: 2,
  useTabs: false,
  semi: true,
  singleQuote: true,
  trailingComma: 'all',
  bracketSpacing: true,
  arrowParens: 'always',
  jsxSingleQuote: true,
  quoteProps: 'as-needed',

  overrides: [
    {
      files: '*.md',
      options: {
        proseWrap: 'preserve',
        tabWidth: 2,
        printWidth: 120,
      },
    },
    {
      files: '*.{yml,yaml,json}',
      options: {
        tabWidth: 2,
        singleQuote: false,
      },
    },
    {
      files: 'Dockerfile*',
      options: {
         useTabs: true,
         tabWidth: 4,
         printWidth: 120,
      },
    },
    {
       files: 'prisma/schema.prisma',
       options: {
          parser: 'prisma',
          singleQuote: false,
          printWidth: 80,
       }
    }
  ],
};
