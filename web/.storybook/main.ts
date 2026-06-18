import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  addons: ['@storybook/addon-docs', '@storybook/addon-a11y'],
  docs: {
    autodocs: 'tag',
  },
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  stories: ['../src/stories/**/*.stories.@(ts|tsx|mdx)'],
};

export default config;
