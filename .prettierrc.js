module.exports = {
  trailingComma: 'all',
  tabWidth: 2,
  semi: true,
  singleQuote: true,
  printWidth: 100,

  overrides: [
    {
      files: '*.md',
      options: {
        proseWrap: 'preserve',
        tabWidth: 2,
      },
    },
    {
      files: '*.{yml,yaml}',
      options: {
        tabWidth: 2,
      },
    },
    {
      files: '*.json',
      options: {
        tabWidth: 2,
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
  ],
};
